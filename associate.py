import sys
import os
from typing_extensions import override
from openai import AssistantEventHandler, OpenAI
import json
from lxml import etree
import zipfile
import shutil
import re

prompt = sys.argv[0]

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

input = "Change the name in all documents to “Amy Alpha” and adjust her salary to $100,000"

assistant = client.beta.assistants.create(
    name="Legal Assistant",
    instructions="""
    Instructions:
        - ensure first names are accounted for be consistent when changing names
    Goal:
        - Perform task assigned by input prompt
    """,
    temperature=0,
    model="gpt-4o",
    tools=[
        {"type": "file_search"},
        {
            "type": "function",
            "function": {
                "name": "replace_text",
                "description": "Replace specific text you give me in document",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text_to_replace": {
                            "type": "string",
                            "description": "Text to be replaced"
                        },
                        "replacement_text": {
                            "type": "string",
                            "description": "Text as replacement for text_to_replace"
                        }
                    },
                    "required": ["text_to_replace", "replacement_text"],
                },
            },
        },
    ],
)

if os.path.isdir("temp"):
    shutil.rmtree("temp")
if os.path.isdir("output"):
    shutil.rmtree("output")


directory = "Employment Agreement"
files = []
for dirpath, dirnames, filenames in os.walk(directory):
    noextensions = map(lambda filename : filename.split('.')[0], filenames)
    files.extend(noextensions)

os.mkdir("temp")
for filename in files:
    unzipped_path = f"temp/{filename}"
    with zipfile.ZipFile(f"{directory}/{filename}.docx", 'r') as zip_ref:
        os.mkdir(unzipped_path)
        zip_ref.extractall(unzipped_path)

    tree = etree.parse(unzipped_path + '/word/document.xml')
    notags = etree.tostring(tree,  method='text', encoding='UTF-8')
    intermediary_file = open(f"{unzipped_path}.txt", "wb+")
    intermediary_file.write(notags)
    intermediary_file.close()


def change_text(current_text: str, arguments):
    to_replace = arguments["text_to_replace"]
    replacement = arguments["replacement_text"]
    pattern = re.compile(to_replace, re.IGNORECASE)
    return pattern.sub(replacement, current_text)

os.mkdir("output")
def zip_directory(folder_path, output_zipfile):
    with zipfile.ZipFile(output_zipfile, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                zipf.write(file_path, os.path.relpath(file_path, folder_path))
for filename in files:
    vector_store = client.beta.vector_stores.create(name=filename)

    file_streams = [open(f"temp/{filename}.txt", "rb")]
    file_batch = client.beta.vector_stores.file_batches.upload_and_poll(
        vector_store_id=vector_store.id, files=file_streams
    )
    assistant = client.beta.assistants.update(
        assistant_id=assistant.id,
        tool_resources={"file_search": {"vector_store_ids": [vector_store.id]}},
    )

    class EventHandler(AssistantEventHandler):
        @override
        def on_text_created(self, text) -> None:
            print("\nassistant > ", end="", flush=True)

        @override
        def on_tool_call_created(self, tool_call):
            pass
        @override
        def on_event(self, event):
            # Retrieve events that are denoted with 'requires_action'
            # since these will have our tool_calls
            if event.event == 'thread.run.requires_action':
                run_id = event.data.id  # Retrieve the run ID from the event data
                self.handle_requires_action(event.data, run_id)

        def handle_requires_action(self, data, run_id):            
            temp_docx_directory = f"temp/{filename}/word/document.xml"
            temp_file = open(temp_docx_directory)
            file_text = temp_file.read()
            temp_file.close()

            for tool in data.required_action.submit_tool_outputs.tool_calls:
                arg_json = json.loads(tool.function.arguments)
                to_replace = arg_json["text_to_replace"]
                replacement = arg_json["replacement_text"]

                print(f"\nchanging \"{to_replace}\" -> \"{replacement}\"")
                file_text = change_text(file_text, arg_json)

            os.remove(temp_docx_directory)

            output_file = open(temp_docx_directory, 'w+')
            output_file.write(file_text)
            output_file.close()

        def submit_tool_outputs(self, tool_outputs, run_id):
            # Use the submit_tool_outputs_stream helper
           with client.beta.threads.runs.submit_tool_outputs_stream(
            thread_id=self.current_run.thread_id,
            run_id=self.current_run.id,
            tool_outputs=tool_outputs,
            event_handler=EventHandler(),
            ) as stream:
                for text in stream.text_deltas:
                    print(text, end="", flush=True)
                print()

        @override
        def on_message_done(self, message) -> None:
            # print a citation to the file searched
            message_content = message.content[0].text
            annotations = message_content.annotations
            citations = []
            for index, annotation in enumerate(annotations):
                message_content.value = message_content.value.replace(
                    annotation.text, f"[{index}]"
                )
                if file_citation := getattr(annotation, "file_citation", None):
                    cited_file = client.files.retrieve(file_citation.file_id)
                    citations.append(f"[{index}] {cited_file.filename}")

            print(message_content.value)
            print("\n".join(citations))

    message_file = client.files.create(
    file=open(f"temp/{filename}.txt", "rb"), purpose="assistants"
    )
    thread = client.beta.threads.create(
        messages=[
            {
                "role": "user",
                "content": input,
                "attachments": [
                    {"file_id": message_file.id, "tools": [{"type": "file_search"}]}
                ],
            }
        ]
    )

    with client.beta.threads.runs.stream(
        thread_id=thread.id,
        assistant_id=assistant.id,
        instructions=input,
        event_handler=EventHandler(),
    ) as stream:
        stream.until_done()
        print(f"\n{filename} is done!")
        zip_directory(f"temp/{filename}", f"output/{filename}.docx")



shutil.rmtree("temp")
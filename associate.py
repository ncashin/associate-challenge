import sys
import os
from openai import OpenAI
import json
from lxml import etree
import zipfile
import shutil

prompt = sys.argv[0]

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

tools = [
        {
            "type": "function",
            "function": {
                "name": "replace_text",
                "description": "replace text in document in all instances",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text_to_replace": {
                            "type": "string",
                            "description": "text currently in document that should be changed add word or two before",
                        },
                        "text_to_change_to": {
                            "type": "string",
                            "description": "text text_to_replace should be changed to",
                        },
                    },
                    "required": ["text_to_replace", "text_to_change_to"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
    ]

input = (
    "Change the name in all documents to “Amy Alpha” and adjust her salary to $100,000"
)

if os.path.isdir("temp"):
    shutil.rmtree("temp")
if os.path.isdir("output"):
    shutil.rmtree("output")


directory = "Employment Agreement"
files = []
for dirpath, dirnames, filenames in os.walk(directory):
    noextensions = map(lambda filename: filename.split(".")[0], filenames)
    files.extend(noextensions)


os.mkdir("temp")
os.mkdir("output")


def zip_directory(folder_path, output_zipfile):
    with zipfile.ZipFile(output_zipfile, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                zipf.write(file_path, os.path.relpath(file_path, folder_path))


def change_text(current_text: str, text_in_document, text_to_change_to):
    print(f'\nchanging text "{text_in_document}" -> "{text_to_change_to}"')

    return current_text.replace(text_in_document, text_to_change_to)


for filename in files:
    print("\n", filename)
    unzipped_path = f"temp/{filename}"
    with zipfile.ZipFile(f"{directory}/{filename}.docx", "r") as zip_ref:
        os.mkdir(unzipped_path)
        zip_ref.extractall(unzipped_path)

    tree = etree.parse(unzipped_path + "/word/document.xml")
    notags = etree.tostring(tree, method="text", encoding="UTF-8")

    client = OpenAI()

    completion = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        messages=[
            {"role": "developer", "content": "you are legal ai"},
            {
                "role": "user",
                "content": f"""
                Input:
                - {input}

                Instructions:
                - MAKE CHANGES TO Document Text BASED ON Input ABOVE AND Document Text BELOW
                - DON'T FILL IN BLANKS UNLESS SPECIFICALLY ASKED
                - MAINTAIN CASE
                - MINIMAL CHANGES PERSERVE MEANING IF POSSIBLE

                Document Text:
                - {notags}
                """,
            },
        ],
        tools=tools,
    )


    temp_docx_directory = f"temp/{filename}/word/document.xml"
    temp_file = open(temp_docx_directory)
    file_text = temp_file.read()
    temp_file.close()

    for tool_call in completion.choices[0].message.tool_calls:
        json_args = json.loads(tool_call.function.arguments)
        print(json_args)
        text_to_replace = json_args["text_to_replace"]
        text_to_change_to = json_args["text_to_change_to"]
        file_text = change_text(file_text, text_to_replace, text_to_change_to)  

    os.remove(temp_docx_directory)

    output_file = open(temp_docx_directory, "w+")
    output_file.write(file_text)
    output_file.close()

    zip_directory(f"temp/{filename}", f"output/{filename}.docx")

shutil.rmtree("temp")

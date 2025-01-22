import sys
import os
from openai import OpenAI
import json
from lxml import etree
import zipfile
import shutil
from functools import reduce


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
                        "description": "text in document to be replaced",
                    },
                    "text_to_insert": {
                        "type": "string",
                        "description": "text that will be inserted where text_to_replace is found",
                    },
                },
                "required": ["text_to_replace", "text_to_insert"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
]


if os.path.isdir("temp"):
    shutil.rmtree("temp")
if os.path.isdir("output"):
    shutil.rmtree("output")


directory = "NVCA"
files = []
for dirpath, dirnames, filenames in os.walk(directory):
    noextensions = map(lambda filename: filename.split(".")[0], filenames)
    files.extend(noextensions)


os.mkdir("temp")
os.mkdir("output")


def find_text_xml(text, text_to_find):
    tag_freeze = False
    found_index = 0
    text_counter = 0
    i = 0
    while i < len(text):
        match text[i]:
            case "<":
                tag_freeze = True
            case ">":
                tag_freeze = False
            case _:
                if not tag_freeze and text[i] == text_to_find[text_counter]:
                    if text_counter == 0:
                        found_index = i
                    
                    text_counter += 1

                    if text_counter == len(text_to_find):
                        return found_index
                    
                elif not tag_freeze and text_counter > 0:
                    text_counter = 0
        i += 1
    return None


def replace_text_xml(text, text_to_replace, text_to_insert):    
    tag_freeze = False
    insertion_counter = 0
    non_frozen_counter = 0

    i = find_text_xml(text, text_to_replace)
    if i is None:
        return text
    
    text = list(text)
    while len(text_to_insert) > insertion_counter or len(text_to_replace) > non_frozen_counter:
        if insertion_counter < len(text_to_insert) and len(text_to_replace) <= non_frozen_counter:
            text.insert(i, text_to_insert[insertion_counter])
            i += 1
            insertion_counter += 1
            non_frozen_counter += 1
            continue

        match text[i]:
            case None:
                return "".join(text)
            case "<":
                tag_freeze = True
            case ">":
                tag_freeze = False
            case _:
                if tag_freeze:
                    break
                else:
                    if insertion_counter >= len(text_to_insert) and len(text_to_replace) > non_frozen_counter:
                        text[i] = ""
                    else:
                        text[i] = text_to_insert[insertion_counter]
                        insertion_counter += 1
                non_frozen_counter += 1
        i += 1

    return "".join(text)

def replace_text(text, text_to_replace, text_to_insert):
        print(f'\Replacing text "{text_to_replace}" -> "{text_to_insert}"')
        updated_text = replace_text_xml(text, text_to_replace, text_to_insert)
        if updated_text == text:
            print("Text not found no replacement")
        else:
            print("Text found and replaced")
        return updated_text

def zip_directory(folder_path, output_zipfile):
    with zipfile.ZipFile(output_zipfile, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                zipf.write(file_path, os.path.relpath(file_path, folder_path))


for filename in files:
    unzipped_path = f"temp/{filename}"
    with zipfile.ZipFile(f"{directory}/{filename}.docx", "r") as zip_ref:
        os.mkdir(unzipped_path)
        zip_ref.extractall(unzipped_path)

tree = etree.parse("temp/acme-motors-term-sheet/word/document.xml")
term_sheet = etree.tostring(tree, method="text", encoding="UTF-8").decode("utf-8")

simplify_term_sheet = False
if simplify_term_sheet:
    completion = client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            messages=[
                {"role": "developer", "content": "The agent is doing legal work"},
                {
                    "role": "user",
                    "content": f"""
                        The agent will minimize the term sheet retaining names and figures given.

                        Term Sheet: \"\"\"
                        {term_sheet}
                        \"\"\"
                        """,
                },
            ],
            tools=tools,
        )
    term_sheet = completion.choices[0].message.content

for filename in files:
    if filename == "acme-motors-term-sheet":
        continue

    print(filename)

    tree = etree.parse(unzipped_path + "/word/document.xml")
    notags = etree.tostring(tree, method="text", encoding="UTF-8").decode("utf-8")

    split_notags = notags.split(" ")
    n = len(split_notags) // 4

    slices = [split_notags[i : i + n] for i in range(0, len(split_notags), n)]

    if len(split_notags) % 4 != 0:
        slices[-1].extend(split_notags[len(slices[0]) * 3 :])

    def concat(a, b):
        return a + " " + b

    slices = list(map(lambda slice: reduce(concat, slice), slices))

    temp_docx_directory = f"temp/{filename}/word/document.xml"
    temp_file = open(temp_docx_directory)
    file_text = temp_file.read()
    temp_file.close()

    i = 0
    for slice in slices:
        i += 1

        completion = client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            messages=[
                {"role": "developer", "content": "The agent is doing legal work"},
                {
                    "role": "user",
                    "content": f"""
                    The agent will return only a single integer without explanation which is the number of blanks to be filled within Document Text.

                    Document Text: \"\"\"
                    {slice}
                    \"\"\"
                    """,
                },
            ],
        )

        number_of_blanks = int(completion.choices[0].message.content)
        print("Number Of Blanks: ", number_of_blanks)
        if number_of_blanks == 0:
            continue

        completion = client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            messages=[
                {"role": "developer", "content": "The agent is doing legal work"},
                {
                    "role": "user",
                    "content": f"""
                    The agent will fill in {number_of_blanks} blanks in Document Text using multiple tool calls if encountering atypical characters using information from Term Sheet.

                    Term Sheet: \"\"\"
                    {term_sheet}
                    \"\"\"

                    Document Text: \"\"\"
                    {slice}
                    \"\"\"
                    """,
                },
            ],
            tools=tools,
        )

        if completion.choices[0].message.tool_calls is None:
            continue

        for tool_call in completion.choices[0].message.tool_calls:
            json_args = json.loads(tool_call.function.arguments)
            
            text_to_replace = json_args["text_to_replace"]
            text_to_insert = json_args["text_to_insert"]

            file_text = replace_text(file_text, text_to_replace, text_to_insert)

    os.remove(temp_docx_directory)

    output_file = open(temp_docx_directory, "w+")
    output_file.write(file_text)
    output_file.close()

    zip_directory(f"temp/{filename}", f"output/{filename}.docx")

shutil.rmtree("temp")

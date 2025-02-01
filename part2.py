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

review_tools = [
    {
        "type": "function",
        "function": {
            "name": "make_edit_suggestion",
            "description": "make suggestion of what to change in the document",
            "parameters": {
                "type": "object",
                "properties": {
                    "suggestion": {
                        "type": "string",
                        "description": "suggestion of what to change in the document",
                    },
                },
                "required": ["suggestion"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_question",
            "description": "ask question about what must be changed in the document",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "question about what must be changed",
                    },
                },
                "required": ["question"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
]
answer_tools = [
    {
        "type": "function",
        "function": {
            "name": "answer_question",
            "description": "answer question asked",
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "integer",
                        "description": "index of question being answered",
                    },
                    "answer": {
                        "type": "string",
                        "description": "answer",
                    },
                },
                "required": ["index", "answer"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
]


edit_tools = [
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

prompt = "The agent will fill in blanks in Document Text based on a Term Sheet"

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
    while (
        len(text_to_insert) > insertion_counter
        or len(text_to_replace) > non_frozen_counter
    ):
        if (
            insertion_counter < len(text_to_insert)
            and len(text_to_replace) <= non_frozen_counter
        ):
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
                    if (
                        insertion_counter >= len(text_to_insert)
                        and len(text_to_replace) > non_frozen_counter
                    ):
                        text[i] = ""
                    else:
                        text[i] = text_to_insert[insertion_counter]
                        insertion_counter += 1
                non_frozen_counter += 1
        i += 1

    return "".join(text)


def replace_text(text, text_to_replace, text_to_insert):
    print(f'Replacing text "{text_to_replace}" -> "{text_to_insert}"')
    updated_text = replace_text_xml(text, text_to_replace, text_to_insert)
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

def format_suggestions(suggestions):
    i = [0]

    def concat_suggestion(a, b, i=i):
        result = a + f"\n\n{i[0]}. {b}"
        i[0] += 1
        return result

    return reduce(concat_suggestion, suggestions, "")


def review_document(document_text: str, prompt: str):
    suggestions = []

    def make_edit_suggestion(args):
        suggestions.append(json.loads(args)["suggestion"])

    # array of array tuples of [question, answer] answer
    questions_and_answers = []

    def ask_question(args):
        questions_and_answers.append([json.loads(args)["question"], None])

    def format_answered_questions(array):
        i = [0]

        def concat_question(a, b, i=i):
            if b[1] is None:
                i[0] += 1
                return a
            result = (
                a
                + f"\n\n{i[0]}. Question: {b[0]} Answer: {'Not yet answered' if b[1] is None else f'{b[1]}'}"
            )
            i[0] += 1
            return result

        return reduce(concat_question, array, "")

    def format_unanswered_questions(array):
        i = [0]

        def concat_question(a, b, i=i):
            if b[1] is not None:
                i[0] += 1
                return a
            result = a + f"\n\n{i[0]}. {b[0]}"
            i[0] += 1
            return result

        return reduce(concat_question, array, "")

    def answer_question(args):
        index = json.loads(args)["index"]
        answer = json.loads(args)["answer"]
        if questions_and_answers[index][1] is None:
            questions_and_answers[index][1] = answer

    i = 0
    max_review_passes = 3
    while i < max_review_passes:
        text_suggestions = format_suggestions(suggestions)
        completion = client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            messages=[
                {"role": "developer", "content": "The agent is doing legal work"},
                {
                    "role": "user",
                    "content": f"""
                        The agent will suggest unique edits based on Document Text.
                        
                        Prompt: \"{prompt}\"

                        Answered Questions:  \"\"\"
                        {format_answered_questions(questions_and_answers)}
                        \"\"\"

                        Previously Suggested Edits:  \"\"\"
                        {text_suggestions}
                        \"\"\"

                        Document Text: \"\"\"
                        {document_text}
                        \"\"\"
                        """,
                },
            ],
            tools=review_tools,
        )

        if completion.choices[0].message.tool_calls is not None:
            for tool_call in completion.choices[0].message.tool_calls:
                match tool_call.function.name:
                    case "make_edit_suggestion":
                        make_edit_suggestion(tool_call.function.arguments)
                    case "ask_question":
                        ask_question(tool_call.function.arguments)

        unanswered_questions = list(
            filter(lambda a: a[1] is None, questions_and_answers)
        )
        if len(unanswered_questions) > 0:
            completion = client.chat.completions.create(
                model="gpt-4o",
                temperature=0,
                messages=[
                    {"role": "developer", "content": "The agent is doing legal work"},
                    {
                        "role": "user",
                        "content": f"""
                        The agent will answer Questions based on Term Sheet without explaining reasoning.
                                        
                        Questions:  \"\"\"
                        {format_unanswered_questions(questions_and_answers)}
                        \"\"\"

                        Term Sheet: \"\"\"
                        {term_sheet}
                        \"\"\"
                        """,
                    },
                ],
                tools=answer_tools,
            )
            if completion.choices[0].message.tool_calls is not None:
                for tool_call in completion.choices[0].message.tool_calls:
                    match tool_call.function.name:
                        case "answer_question":
                            answer_question(tool_call.function.arguments)
        else:
            break
        i += 1

    return suggestions


for filename in files:
    if filename == "acme-motors-term-sheet":
        continue

    tree = etree.parse(unzipped_path + "/word/document.xml")
    notags = etree.tostring(tree, method="text", encoding="UTF-8").decode("utf-8")

    """
    split_notags = notags.split(" ")
    n = len(split_notags) // 4

    slices = [split_notags[i : i + n] for i in range(0, len(split_notags), n)]

    if len(split_notags) % 4 != 0:
        slices[-1].extend(split_notags[len(slices[0]) * 3 :])

    def concat(a, b):
        return a + " " + b
    """

    suggestions = review_document(notags, prompt)
    if len(suggestions) == 0:
        print("No suggestions made not editing document")
        continue

    formatted_suggestions = format_suggestions(suggestions)
    print("Suggestions:", formatted_suggestions)

    completion = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        messages=[
            {"role": "developer", "content": "The agent is doing legal work"},
            {
                "role": "user",
                "content": f"""
                The agent will edit the document based on Edit Suggestions.
                
                Edit Suggestions: \"\"\"
                {formatted_suggestions}
                \"\"\"

                Document Text: \"\"\"
                {notags}
                \"\"\"
                """,
            },
        ],
        tools=edit_tools,
    )
    temp_docx_directory = f"temp/{filename}/word/document.xml"
    temp_file = open(temp_docx_directory)
    file_text = temp_file.read()
    temp_file.close()

    if completion.choices[0].message.tool_calls is None:
        continue

    failed_edits = ""
    for tool_call in completion.choices[0].message.tool_calls:
        json_args = json.loads(tool_call.function.arguments)

        text_to_replace = json_args["text_to_replace"]
        text_to_insert = json_args["text_to_insert"]

        updated_text = replace_text(file_text, text_to_replace, text_to_insert)
        if updated_text == file_text:
            print("Text not found no replacement")
            failed_edits += f'"{text_to_replace}" -> "{text_to_insert}"\n'
        else:
            print("Text found and replaced")
            file_text = updated_text

    if len(failed_edits) > 0:
        completion = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        messages=[
            {"role": "developer", "content": "The agent is doing legal work"},
            {
                "role": "user",
                "content": f"""
                The agent will attempt to change make changes on Document Text 
                
                Failed Edits: \"\"\"
                {failed_edits}
                \"\"\"

                Document Text: \"\"\"
                {notags}
                \"\"\"
                """,
            },
        ],
        tools=edit_tools,
    )
        for tool_call in completion.choices[0].message.tool_calls:
            json_args = json.loads(tool_call.function.arguments)

            text_to_replace = json_args["text_to_replace"]
            text_to_insert = json_args["text_to_insert"]

            updated_text = replace_text(file_text, text_to_replace, text_to_insert)
            if updated_text == file_text:
                print("Text not found no replacement")
                failed_edits += f'"{text_to_replace}" -> "{text_to_insert}"\n'
            else:
                print("Text found and replaced")
                file_text = updated_text


    os.remove(temp_docx_directory)

    output_file = open(temp_docx_directory, "w+")
    output_file.write(file_text)
    output_file.close()

    zip_directory(f"temp/{filename}", f"output/{filename}.docx")

shutil.rmtree("temp")

"""
review pass -> what needs to be changed | returns suggestion or question | (edit repeat until no questions)

editing pass -> make changes based on suggestions

verification pass -> ensure correctness
"""

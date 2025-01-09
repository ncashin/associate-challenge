import os
import zipfile

def zip_directory(folder_path, output_zipfile):
    with zipfile.ZipFile(output_zipfile, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                zipf.write(file_path, os.path.relpath(file_path, folder_path))

# Example usage
folder_to_zip = 'test'  # Replace with your directory path
output_zip = 'test.docx'  # Replace with desired output zip file name

zip_directory(folder_to_zip, output_zip)
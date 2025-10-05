import os

def collect_source_code(source_dir, output_dir):
    """
    Traverses a source directory, reads the content of all files in its subdirectories,
    and saves the content of each subdirectory into a separate text file in the output directory.

    Args:
        source_dir (str): The path to the source directory to be processed.
        output_dir (str): The path to the directory where the output text files will be saved.
    """
    # Create the output directory if it does not already exist
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Recursively walk through the source directory
    for dirpath, _, filenames in os.walk(source_dir):
        # Skip the root source directory itself, only process subdirectories
        if dirpath == source_dir:
            continue

        # Get the base name of the current directory
        subdirectory_name = os.path.basename(dirpath)
        output_filename = f"{subdirectory_name}.txt"
        output_filepath = os.path.join(output_dir, output_filename)

        # Open the output file in append mode to gather all file contents
        with open(output_filepath, 'a', encoding='utf-8') as outfile:
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as infile:
                        outfile.write(f"--- Content from: {filename} ---\n")
                        outfile.write(infile.read())
                        outfile.write("\n\n")
                except Exception as e:
                    print(f"Error reading file {file_path}: {e}")

if __name__ == "__main__":
    # --- Configuration ---
    # Replace this with the path to your Google Agent Development Package
    SOURCE_DIRECTORY = "/home/srikanth/Work/AI Agents/software_engineer_agent/.venv/lib/python3.12/site-packages/google/adk"
    # Replace this with the path where you want to save the output text files
    OUTPUT_DIRECTORY = "/home/srikanth/Work/AI Agents/software_engineer_agent/output"
    # -------------------

    if not os.path.isdir(SOURCE_DIRECTORY):
        print(f"Error: The source directory '{SOURCE_DIRECTORY}' does not exist.")
    else:
        collect_source_code(SOURCE_DIRECTORY, OUTPUT_DIRECTORY)
        print(f"Source code has been collected and saved in '{OUTPUT_DIRECTORY}'")
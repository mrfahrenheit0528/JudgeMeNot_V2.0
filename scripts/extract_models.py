import re

def extract(xml_path, file_target, dest):
    print(f"Extracting {file_target} from {xml_path}...")
    with open(xml_path, 'r', encoding='utf-8') as f:
        content = f.read()
    m = re.search(f'<file path="{file_target}">\n(.*?)\n</file>', content, re.DOTALL)
    if m:
        with open(dest, 'w', encoding='utf-8') as out:
            out.write(m.group(1))
        print(f"Extracted to {dest}")
    else:
        print(f"Could not find {file_target}")

extract(r'context\repomix-output(JudgeMeNot_v1).xml', 'models/all_models.py', 'v1_models_extracted.py')
extract(r'context\repomix-output(Stable QuizBee System).xml', 'website/models.py', 'qb_models_extracted.py')

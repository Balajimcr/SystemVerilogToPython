# Refactored XML to SystemVerilog Converter

import xml.etree.ElementTree as ET
import re

# Modular formatting helpers

def format_identifier(text):
    return re.sub(r'\W|^(?=\d)', '_', text)

# Entity decoding using str.maketrans
entity_translation = str.maketrans({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '\"': '&quot;',
    "'": '&apos;'
})

def decode_entity(text):
    return text.translate(entity_translation)

def collect_blocks(root):
    blocks = []
    for child in root:
        blocks.append(child)
        blocks.extend(collect_blocks(child))
    return blocks

def process_xml(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()
    blocks = collect_blocks(root)

    for block in blocks:
        # Do something with each block
        print(block.tag, format_identifier(block.text))

if __name__ == '__main__':
    xml_file_path = 'input.xml'  # Example input file
    process_xml(xml_file_path)
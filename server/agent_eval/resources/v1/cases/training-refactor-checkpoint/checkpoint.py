import json

def write_metadata(metadata_path, metadata):
    metadata_path.write_text(json.dumps(metadata))

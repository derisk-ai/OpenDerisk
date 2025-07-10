import json
import pandas as pd

def get_eval_datasets(file_path: str, out_path: str = None) -> list[dict]:
    """
    Process the Excel file and return a list of dictionaries representing each row.
    """

    if not out_path:
        out_path = file_path.replace('.csv', '.json')
    
    df = pd.read_csv(file_path) 
    data = []
    for _, row in df.iterrows():
        task_index, instruction, scoring_points = row
        query = instruction.strip() if instruction else ""
        answer = scoring_points.strip() if scoring_points else ""
        data.append({"query": query, "answer": answer, "task_index": task_index}) 
        
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    return data

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Process an Excel file and output a JSON file.")
    parser.add_argument("--file_path", type=str, help="Path to the input Excel file.")
    parser.add_argument("--out_path", type=str, default=None, help="Path to the output JSON file (optional).")

    args = parser.parse_args()

    datasets = get_eval_datasets(args.file_path, args.out_path)
    print(f"Processed {len(datasets)} records.") 
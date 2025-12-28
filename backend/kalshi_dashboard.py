import os
import json
# ... (rest of your imports)

def save_report(summary_data):
    # This path puts the data inside the docs folder so the site can see it
    output_path = "docs/data/kalshi_summary.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(summary_data, f, indent=4)
    print(f"Data saved to {output_path}")

# Call save_report(summary) at the end of your main() function

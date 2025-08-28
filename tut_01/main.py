import streamlit as st
import pandas as pd
import shutil, time
import re, os

# ---------------------- Helper Utilities ----------------------

def setup_directories():
    """Create necessary output directories"""
    base = "results"
    os.makedirs(base, exist_ok=True)

    dirs = {
        "base": base,
        "branchwise": os.path.join(base, "branchwise_split"),
        "uniform": os.path.join(base, "uniform_groups"),
        "mixed": os.path.join(base, "mixed_groups")
    }

    for path in dirs.values():
        os.makedirs(path, exist_ok=True)

    return dirs

def save_csv(data, columns, path):
    """Save list of rows as CSV"""
    df = pd.DataFrame(data, columns=columns)
    df.to_csv(path, index=False)


# ---------------------- Grouping Functions ----------------------

def split_by_branch(df, columns, dirs):
    """Separate students into branch-based files"""
    pattern = re.compile(r'^[0-9]{4}([A-Za-z]{2})[0-9]{2}')
    grouped = {}

    for _, row in df.iterrows():
        match = pattern.match(str(row['Roll']))
        if match:
            code = match.group(1).upper()
            grouped.setdefault(code, []).append(row.tolist())
        else:
            print("Invalid Roll Number:", row['Roll'])

    for code, rows in grouped.items():
        save_csv(rows, columns, os.path.join(dirs["branchwise"], f"{code}.csv"))

    return grouped, "Branchwise files created successfully."


def uniform_distribution(branch_data, columns, group_count, dirs):
    """Distribute students uniformly regardless of branch"""
    ordered = dict(sorted(branch_data.items(), key=lambda x: len(x[1]), reverse=True))
    merged = pd.concat([pd.DataFrame(v, columns=columns) for v in ordered.values()],
                       ignore_index=True)

    total = len(merged)
    size, remainder = divmod(total, group_count)
    pointer = 0

    for i in range(group_count):
        start, end = pointer, pointer + size + (1 if remainder > 0 else 0)
        subset = merged.iloc[start:end, :]
        remainder -= 1 if remainder > 0 else 0
        pointer = end
        subset.to_csv(os.path.join(dirs["uniform"], f"group_{i+1}.csv"), index=False)

    return "Uniform groups saved."


def mixed_distribution(branch_data, columns, group_count, dirs):
    """Distribute students mixing branch proportionally"""
    total_students = sum(len(v) for v in branch_data.values())
    size, remainder = divmod(total_students, group_count)

    pools = {b: list(students) for b, students in branch_data.items()}
    groups = [[] for _ in range(group_count)]

    # Fill groups evenly
    for i in range(group_count):
        while len(groups[i]) < size and pools:
            for branch in list(pools.keys()):
                if pools[branch]:
                    groups[i].append(pools[branch].pop(0))
                if not pools[branch]:
                    del pools[branch]
                if len(groups[i]) == size:
                    break

    # Handle leftovers
    leftovers = []
    for rest in pools.values():
        leftovers.extend(rest)

    idx = 0
    while leftovers:
        groups[idx % group_count].append(leftovers.pop(0))
        idx += 1

    # Save
    for i, grp in enumerate(groups, start=1):
        save_csv(grp, columns, os.path.join(dirs["mixed"], f"group_{i}.csv"))

    return "Mixed groups saved."


def generate_summary(dirs, roll_col="Roll"):
    """Generate stats for groups"""
    regex = r'^(?:\d{4}([A-Za-z]{2})\d{2}|([A-Za-z]{2}))$'

    def read_stats(folder):
        stats = {}
        files = sorted([f for f in os.listdir(folder) if f.endswith(".csv")],
                       key=lambda x: int(re.search(r'(\d+)', x).group(1)) if re.search(r'(\d+)', x) else 0)

        for idx, f in enumerate(files, start=1):
            df = pd.read_csv(os.path.join(folder, f))
            extracted = df[roll_col].astype(str).str.extract(regex)
            codes = (extracted[0].fillna(extracted[1]) if 1 in extracted.columns else extracted[0]).str.upper()
            counts = codes.value_counts()
            stats[f"G{idx}"] = counts.to_dict()
            stats[f"G{idx}"]["Total"] = len(df)

        if not stats:
            return pd.DataFrame(columns=["Group", "Total"])

        tab = pd.DataFrame(stats).fillna(0).astype(int).T
        cols = sorted([c for c in tab.columns if c != "Total"])
        tab = tab[cols + ["Total"]]
        tab.insert(0, "Group", tab.index)
        return tab.reset_index(drop=True)

    uniform_df = read_stats(dirs["uniform"])
    mixed_df = read_stats(dirs["mixed"])

    # Align columns
    cols = uniform_df.columns if not uniform_df.empty else (mixed_df.columns if not mixed_df.empty else ["Group", "Total"])
    mixed_df = mixed_df.reindex(columns=cols, fill_value=0)

    header_uniform = pd.DataFrame([["Uniform"] + [""] * (len(cols) - 1)], columns=cols)
    header_mixed = pd.DataFrame([["Mixed"] + [""] * (len(cols) - 1)], columns=cols)
    gap = pd.DataFrame([[""] * len(cols)], columns=cols)

    final = pd.concat([header_uniform, uniform_df, gap, header_mixed, mixed_df], ignore_index=True)
    final.to_csv(os.path.join(dirs["base"], "summary.csv"), index=False)

    return "Stats file saved.", final


# ---------------------- Streamlit UI ----------------------

def main():
    min_size = 1

    with st.form(key='group_form'):
        group_count = st.number_input('Number of Groups', min_value=min_size, step=1, value=min_size)
        input_file = st.file_uploader("Upload Excel File", type=["xlsx", "xls"])
        submit = st.form_submit_button('Generate Groups')

    if submit:
        if input_file is not None:
            try:
                with st.spinner("Processing file... ⏳"):
                    time.sleep(2)

                    df = pd.read_excel(input_file)
                    dirs = setup_directories()
                    branchwise, msg1 = split_by_branch(df, df.columns, dirs)

                    msg2 = uniform_distribution(branchwise, df.columns, group_count, dirs)

                    msg3 = mixed_distribution(branchwise, df.columns, group_count, dirs)

                    msg4, stats_df = generate_summary(dirs)
                    st.write(msg4)

                    # Zip output
                    zip_path = shutil.make_archive("results", "zip", "results")
                with open(zip_path, "rb") as f:
                    st.download_button("Download Results (ZIP)", f, "results.zip", "application/zip")

            except Exception as e:
                st.error(f"Error: {e}")
        else:
            st.warning("Please upload a file to continue.")

main()
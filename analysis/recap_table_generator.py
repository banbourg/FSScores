import pandas as pd

import sys
import os

p_list = [os.path.abspath("../scraper/"), os.path.abspath("..")]
for p in p_list:
    if p not in sys.path:
        sys.path.append(p)

try:
    import settings
    import db_builder
except ImportError as exc:
    sys.exit(f"Error: failed to import module ({exc})")

# ------------------------------------------ CHANGE RUN PARAMETERS HERE ------------------------------------------------
name = 'JGPARM'
season = 'sb2018'
target_disc_list = ["IceDance", "Men", "Ladies"]#, "Pairs"]
db_credentials = settings.DB_CREDENTIALS
# ----------------------------------------------------------------------------------------------------------------------

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 1900)

MASTER_DICT = {"IceDance": ["twizzles", "lift", "pattern dance"],
               "Men": ["jump"],
               "Pairs": ["throw jump", "throw twist", "jump"],
               "Ladies": ["jump"]}


def reconstitute_elt(row):
    if row["element_type"] == "pattern dance":
        fields = [row["element_name"], row["elt_level"]]
        if row["interruption_flag"] == 1:
            fields.append("!")

    elif row["element_type"] == "lift":
        if row["elt_1_name"]:
            fields = [row["elt_1_name"], row["elt_1_level"], "+", row["elt_2_name"], row["elt_2_level"]]
        else:
            fields = [row["element_name"], row["elt_level"]]

    elif row["element_type"] == "twizzles":
        fields = [row["element_name"], "L", row["elt_level_lady"], "+M", row["elt_level_man"]]

    elif row["element_type"] in ["throw jump", "throw twist"]:
        fields = [row["element_name"], row["elt_level"]]
        if row["ur_flag"] == 1:
            fields.append("<")
        elif row["downgrade_flag"] == 1:
            fields.append("<<")

    elif row["element_type"] == "jump" and row["combo_flag"] == 1 or row["seq_flag"] == 1:
        no_elements = row["element_name"].count("+") + 1

        fields = []
        for i in range(1, no_elements+1):
            fields.append(row["jump_" + str(i)])
            if row["jump_" + str(i) + "_unc_edge"] == 1:
                fields.append("!")
            elif row["jump_" + str(i) + "_sev_edge"] == 1:
                fields.append("e")
            if row["jump_" + str(i) + "_ur"] == 1:
                fields.append("<")
            elif row["jump_" + str(i) + "_downgrade"] == 1:
                fields.append("<<")
            fields.append("+")

        if row["rep_flag"] == 1:
            fields.append("REP" if fields[-1] == "+" else "+REP")
        if row["seq_flag"] == 1:
            fields.append("SEQ" if fields[-1] == "+" else "+SEQ")
        if row["element_name"].count("+") == 0:
            fields.append("COMBO" if fields[-1] == "+" else "+COMBO")

        if fields[-1] == "+":
            fields = fields[:-1]

    else:
        fields = [row["element_name"]]
        if row["unc_edge_flag"] == 1:
            fields.append("!")
        elif row["sev_edge_flag"] == 1:
            fields.append("e")
        if row["ur_flag"] == 1:
            fields.append("<")
        elif row["downgrade_flag"] == 1:
            fields.append("<<")
    
    if row["invalid_flag"] == 1:
        fields.append("*")

    fields = [f for f in fields if f is not None]
    element = "".join(fields)
    return element


def create_recap_table(disc, df, writer):
    disc_df = df[(df["discipline"] == disc) & (df["element_type"].isin(MASTER_DICT[disc]))
                 & ~(df["element"].str.contains("Ch"))]

    disc_df.drop(axis="columns", labels=["discipline"], inplace=True)

    # Concatenate layout
    if disc in ["Men", "Ladies"]:
        grouped_df_1 = disc_df.groupby(["competitor", "sb2018_fed", "segment", "tss", "h2_bonus_flag"], as_index=False)\
            .apply(lambda x: " ".join(x["element"])).reset_index()
        grouped_df_1.rename(columns={0: "layout_half"}, inplace=True)
        grouped_df = grouped_df_1.groupby(["competitor", "sb2018_fed", "segment", "tss"], as_index=False) \
            .apply(lambda x: " // ".join(x["layout_half"])).reset_index()
    else:
        grouped_df = disc_df.groupby(["competitor", "sb2018_fed", "segment", "tss"], as_index=False)\
            .apply(lambda x: " ".join(x["element"])).reset_index()

    # Reshape
    grouped_df.set_index(["competitor", "sb2018_fed", "segment"], inplace=True)
    unstacked = grouped_df.rename(columns={0: "layout"}).unstack(level=-1)
    unstacked.columns = unstacked.columns.map(" ".join).str.strip()

    unstacked.dropna(axis="index", inplace=True)

    # Total TSS
    dic = {"short": "RD" if disc == "IceDance" else "SP", "long": "FD" if disc == "IceDance" else "FS"}
    unstacked["total"] = unstacked["tss " + dic["short"]] + unstacked["tss " + dic["long"]]

    # Get segment rankings
    for l in dic:
        unstacked[l+" rank"] = unstacked["tss "+dic[l]].rank(axis=0, ascending=False, method="min")
        unstacked[l] = unstacked.apply(lambda x: '{0:.2f}'.format((x["tss "+dic[l]])) + " (#" + str(x[l+" rank"])[:-2] + ")", axis=1)
        unstacked.drop(axis="columns", labels=[l+" rank", "tss "+dic[l]], inplace=True)

    unstacked = unstacked[unstacked.columns[[1, 3, 0, 4, 2]]]
    unstacked.sort_values("total", axis=0, ascending=False, inplace=True)
    unstacked.apply(lambda x: '{0:.2f}'.format(x["total"]), axis=1)
    unstacked = unstacked.head(5)
    unstacked.to_excel(writer, sheet_name=disc)


def main(name, season):
    conn, engine = db_builder.initiate_connections(db_credentials)

    query = f"""
    SELECT segments.discipline, competitors.competitor_name, competitors.sb2018_fed, segments.segment, protocols.tss, elements.* FROM elements
        JOIN protocols on protocol_id = protocols.id
        JOIN segments on protocols.segment_id = segments.id
        JOIN competitors on protocols.competitor_id = competitors.id
    WHERE segments.name = '{name}' AND segments.season = '{season}' AND elements.element_type IN ('jump', 'twizzles', 'pattern dance', 'lift', 'throw jump', 'throw twist');"""

    df = pd.read_sql_query(query, engine)
    df["competitor"] = df.apply(lambda x: x["competitor_name"].title(), axis=1)
    df["element"] = df.apply(reconstitute_elt, axis=1)

    col_list = ["discipline", "segment", "competitor", "sb2018_fed", "tss", "element_no", "element_type", "element", "h2_bonus_flag"]
    clean_df = df[col_list]
    clean_df.sort_values("element_no", axis=0, ascending=True, inplace=True)

    writer = pd.ExcelWriter(settings.WRITE_PATH+name+season+".xlsx")

    for disc in target_disc_list:
        create_recap_table(disc, clean_df, writer)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        main(name, season)
    else:
        main(sys.argv[1], sys.argv[2])

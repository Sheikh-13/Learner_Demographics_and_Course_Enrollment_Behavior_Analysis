import math
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------
DATA_FILE = Path(__file__).parent / "EduPro_Online_Platform.xlsx"

AGE_LABELS = ["<18", "18–25", "26–35", "36–45", "45+"]
AGE_BINS = [-1, 17, 25, 35, 45, 200]
LEVEL_ORDER = ["Beginner", "Intermediate", "Advanced"]
LEVEL_SCORE = {"Beginner": 1, "Intermediate": 2, "Advanced": 3}

st.set_page_config(
    page_title="EduPro – Learner Demographics & Enrollment Behavior",
    layout="wide",
)


# ----------------------------------------------------------------------------
# Data integration
# ----------------------------------------------------------------------------
@st.cache_data
def load_data():
    users = pd.read_excel(
        DATA_FILE, sheet_name="Users",
        usecols=["UserID", "UserName", "Age", "Gender"],
    )
    courses = pd.read_excel(
        DATA_FILE, sheet_name="Courses",
        usecols=["CourseID", "CourseName", "CourseCategory", "CourseType", "CourseLevel"],
    )
    transactions = pd.read_excel(
        DATA_FILE, sheet_name="Transactions",
        usecols=["TransactionID", "UserID", "CourseID", "TransactionDate"],
    )

    # Referential-integrity checks
    checks = {
        "Duplicate UserID in Users": int(users["UserID"].duplicated().sum()),
        "Duplicate CourseID in Courses": int(courses["CourseID"].duplicated().sum()),
        "Duplicate TransactionID": int(transactions["TransactionID"].duplicated().sum()),
        "Transactions with unknown UserID": int((~transactions["UserID"].isin(users["UserID"])).sum()),
        "Transactions with unknown CourseID": int((~transactions["CourseID"].isin(courses["CourseID"])).sum()),
    }

    # Users <-> Transactions <-> Courses (inner joins keep only valid links)
    df = (
        transactions
        .merge(users, on="UserID", how="inner", validate="m:1")
        .merge(courses, on="CourseID", how="inner", validate="m:1")
    )

    df["AgeGroup"] = pd.cut(df["Age"], bins=AGE_BINS, labels=AGE_LABELS)

    # Learner segment: average course level over ALL of a learner's enrollments
    df["LevelScore"] = df["CourseLevel"].map(LEVEL_SCORE)
    avg_level = df.groupby("UserID")["LevelScore"].mean()
    learner_level = pd.cut(
        avg_level, bins=[0, 5 / 3, 7 / 3, 3], labels=LEVEL_ORDER
    ).astype(str)
    df["LearnerLevel"] = df["UserID"].map(learner_level)

    return df, checks


def count_by(frame, col, order=None):
    counts = frame[col].value_counts()
    if order is not None:
        counts = counts.reindex(order, fill_value=0)
    return counts.rename_axis(col).reset_index(name="Enrollments")


try:
    data, integrity = load_data()
except FileNotFoundError:
    st.error(f"Data file not found. Place '{DATA_FILE.name}' in the same folder as app.py.")
    st.stop()

# ----------------------------------------------------------------------------
# Sidebar filters
# ----------------------------------------------------------------------------
st.sidebar.header("Filters")
sel_age = st.sidebar.multiselect("Age group", AGE_LABELS, default=AGE_LABELS)
sel_gender = st.sidebar.multiselect(
    "Gender", sorted(data["Gender"].unique()), default=sorted(data["Gender"].unique())
)
sel_cat = st.sidebar.multiselect(
    "Course category", sorted(data["CourseCategory"].unique()),
    default=sorted(data["CourseCategory"].unique()),
)
sel_level = st.sidebar.multiselect("Course level", LEVEL_ORDER, default=LEVEL_ORDER)

with st.sidebar.expander("Data integrity checks"):
    for label, value in integrity.items():
        st.write(f"{label}: **{value}**")

f = data[
    data["AgeGroup"].isin(sel_age)
    & data["Gender"].isin(sel_gender)
    & data["CourseCategory"].isin(sel_cat)
    & data["CourseLevel"].isin(sel_level)
]

st.title("EduPro – Learner Demographics & Course Enrollment Behavior")

if f.empty:
    st.warning("No enrollments match the selected filters. Adjust the filters in the sidebar.")
    st.stop()

# Per-learner table (based on the filtered enrollments)
per_learner = (
    f.groupby("UserID")
    .agg(
        Age=("Age", "first"),
        AgeGroup=("AgeGroup", "first"),
        Gender=("Gender", "first"),
        LearnerLevel=("LearnerLevel", "first"),
        Courses=("TransactionID", "count"),
    )
    .reset_index()
)

total_enrollments = len(f)
total_learners = len(per_learner)

# ----------------------------------------------------------------------------
# Tabs
# ----------------------------------------------------------------------------
tab_overview, tab_age, tab_gender, tab_cat, tab_behavior = st.tabs(
    [
        "Learner Demographic Overview",
        "Age-wise Enrollment",
        "Gender-based Course Preference",
        "Course Category Popularity",
        "Behavioral Insights",
    ]
)

# ---------------------------- Overview --------------------------------------
with tab_overview:
    gender_learners = per_learner["Gender"].value_counts()
    if "Female" in gender_learners.index and "Male" in gender_learners.index:
        ratio_text = f"{gender_learners['Female'] / gender_learners['Male']:.2f} : 1"
    else:
        ratio_text = "n/a"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Enrollments", f"{total_enrollments:,}")
    c2.metric("Active Learners", f"{total_learners:,}")
    c3.metric("Avg Courses per Learner", f"{total_enrollments / total_learners:.2f}")
    c4.metric("Gender Participation Ratio (Female : Male learners)", ratio_text)

    left, right = st.columns(2)
    with left:
        age_hist = px.histogram(
            per_learner, x="Age", nbins=per_learner["Age"].nunique(),
            title="Age Distribution of Learners",
        )
        age_hist.update_layout(yaxis_title="Learners", bargap=0.05)
        st.plotly_chart(age_hist, width="stretch")
    with right:
        gender_pie = px.pie(
            gender_learners.rename_axis("Gender").reset_index(name="Learners"),
            names="Gender", values="Learners", hole=0.45,
            title="Gender Distribution of Learners",
        )
        st.plotly_chart(gender_pie, width="stretch")

    st.subheader("Participation by demographic group")
    participation = (
        f.groupby(["AgeGroup", "Gender"], observed=False)
        .agg(Learners=("UserID", "nunique"), Enrollments=("TransactionID", "count"))
        .reset_index()
    )
    participation["Enrollments per Learner"] = (
        participation["Enrollments"] / participation["Learners"].where(participation["Learners"] > 0)
    ).round(2)
    st.dataframe(participation, width="stretch", hide_index=True)

# ---------------------------- Age-wise --------------------------------------
with tab_age:
    age_counts = count_by(f, "AgeGroup", AGE_LABELS)
    fig = px.bar(
        age_counts, x="AgeGroup", y="Enrollments", text="Enrollments",
        category_orders={"AgeGroup": AGE_LABELS},
        title="Enrollments by Age Group",
    )
    fig.update_layout(xaxis_title="Age Group")
    st.plotly_chart(fig, width="stretch")

    st.subheader("Age group vs course category")
    heat = (
        pd.crosstab(f["AgeGroup"], f["CourseCategory"])
        .reindex(AGE_LABELS, fill_value=0)
    )
    heat_fig = px.imshow(
        heat, text_auto=True, aspect="auto", color_continuous_scale="Blues",
        labels=dict(x="Course Category", y="Age Group", color="Enrollments"),
    )
    st.plotly_chart(heat_fig, width="stretch")

    st.subheader("Age group vs course level")
    age_level = (
        f.groupby(["AgeGroup", "CourseLevel"], observed=False)
        .size().reset_index(name="Enrollments")
    )
    level_fig = px.bar(
        age_level, x="AgeGroup", y="Enrollments", color="CourseLevel", barmode="group",
        category_orders={"AgeGroup": AGE_LABELS, "CourseLevel": LEVEL_ORDER},
    )
    level_fig.update_layout(xaxis_title="Age Group")
    st.plotly_chart(level_fig, width="stretch")

# ---------------------------- Gender-based ----------------------------------
with tab_gender:
    cat_gender = f.groupby(["CourseCategory", "Gender"]).size().reset_index(name="Enrollments")
    st.plotly_chart(
        px.bar(
            cat_gender, x="CourseCategory", y="Enrollments", color="Gender",
            barmode="group", title="Course Category Enrollments by Gender",
        ),
        width="stretch",
    )

    lv_gender = f.groupby(["CourseLevel", "Gender"]).size().reset_index(name="Enrollments")
    ty_gender = f.groupby(["CourseType", "Gender"]).size().reset_index(name="Enrollments")
    g1, g2 = st.columns(2)
    with g1:
        st.plotly_chart(
            px.bar(
                lv_gender, x="CourseLevel", y="Enrollments", color="Gender",
                barmode="group", category_orders={"CourseLevel": LEVEL_ORDER},
                title="Course Level by Gender",
            ),
            width="stretch",
        )
    with g2:
        st.plotly_chart(
            px.bar(
                ty_gender, x="CourseType", y="Enrollments", color="Gender",
                barmode="group", title="Course Type by Gender",
            ),
            width="stretch",
        )

    st.subheader("Share of each gender's enrollments by category (%)")
    share = (
        pd.crosstab(f["CourseCategory"], f["Gender"], normalize="columns") * 100
    ).round(1)
    st.dataframe(share, width="stretch")

# ---------------------------- Category popularity ---------------------------
with tab_cat:
    cat = count_by(f, "CourseCategory")
    cat["Share (%)"] = (cat["Enrollments"] / total_enrollments * 100).round(1)
    cat["Category Popularity Index"] = (
        cat["Enrollments"] / cat["Enrollments"].mean() * 100
    ).round(1)
    cat = cat.sort_values("Enrollments", ascending=False)

    st.caption("Category Popularity Index = category enrollments ÷ average enrollments per category × 100 (100 = average).")
    st.plotly_chart(
        px.bar(
            cat, x="CourseCategory", y="Category Popularity Index",
            text="Category Popularity Index", title="Category Popularity Index",
        ),
        width="stretch",
    )

    m1, m2 = st.columns(2)
    m1.success(f"Most popular: {cat.iloc[0]['CourseCategory']} ({int(cat.iloc[0]['Enrollments']):,} enrollments)")
    m2.info(f"Least popular: {cat.iloc[-1]['CourseCategory']} ({int(cat.iloc[-1]['Enrollments']):,} enrollments)")

    t1, t2 = st.columns(2)
    with t1:
        st.plotly_chart(
            px.bar(
                count_by(f, "CourseType"), x="CourseType", y="Enrollments",
                text="Enrollments", title="Enrollments by Course Type",
            ),
            width="stretch",
        )
    with t2:
        st.plotly_chart(
            px.bar(
                count_by(f, "CourseLevel", LEVEL_ORDER), x="CourseLevel", y="Enrollments",
                text="Enrollments", title="Level Preference Distribution",
            ),
            width="stretch",
        )

    st.dataframe(cat, width="stretch", hide_index=True)

# ---------------------------- Behavioral insights ---------------------------
with tab_behavior:
    top_n = max(1, math.ceil(0.10 * total_learners))
    top_share = per_learner["Courses"].nlargest(top_n).sum() / total_enrollments * 100

    b1, b2, b3 = st.columns(3)
    b1.metric("Average Courses per Learner", f"{per_learner['Courses'].mean():.2f}")
    b2.metric("Median Courses per Learner", f"{per_learner['Courses'].median():.0f}")
    b3.metric("Enrollments from Top 10% Most Active Learners", f"{top_share:.1f}%")

    dist = per_learner["Courses"].value_counts().sort_index().rename_axis("Courses Taken").reset_index(name="Learners")
    st.plotly_chart(
        px.bar(dist, x="Courses Taken", y="Learners", text="Learners",
               title="Learners by Number of Courses Taken"),
        width="stretch",
    )

    st.subheader("Beginner vs Intermediate vs Advanced learners")
    st.caption(
        "Learner segment = average course level across all of a learner's enrollments "
        "(Beginner = 1, Intermediate = 2, Advanced = 3). "
        "≤ 1.67 → Beginner, ≤ 2.33 → Intermediate, above → Advanced."
    )
    seg = (
        per_learner.groupby("LearnerLevel")
        .agg(Learners=("UserID", "count"), AvgCourses=("Courses", "mean"))
        .reindex(LEVEL_ORDER)
        .reset_index()
    )
    seg["AvgCourses"] = seg["AvgCourses"].round(2)
    st.dataframe(seg, width="stretch", hide_index=True)

    s1, s2 = st.columns(2)
    with s1:
        seg_type = f.groupby(["LearnerLevel", "CourseType"]).size().reset_index(name="Enrollments")
        st.plotly_chart(
            px.bar(
                seg_type, x="LearnerLevel", y="Enrollments", color="CourseType",
                barmode="group", category_orders={"LearnerLevel": LEVEL_ORDER},
                title="Course Type by Learner Segment",
            ),
            width="stretch",
        )
    with s2:
        seg_cat = (
            pd.crosstab(f["LearnerLevel"], f["CourseCategory"])
            .reindex([l for l in LEVEL_ORDER if l in f["LearnerLevel"].unique()])
        )
        st.plotly_chart(
            px.imshow(
                seg_cat, text_auto=True, aspect="auto", color_continuous_scale="Blues",
                labels=dict(x="Course Category", y="Learner Segment", color="Enrollments"),
                title="Category Preference by Learner Segment",
            ),
            width="stretch",
        )

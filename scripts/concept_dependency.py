import sqlite3
from collections import defaultdict
from typing import Dict, List


# =========================================================
# 1. LOAD MAPPING (SYSTEM <-> CONTENT)
# =========================================================
def load_mapping(tutor_db: str):
    """
    Loads concept_id_map from tutor.db

    Purpose:
    - Convert content IDs (P1, H1, etc.) → system IDs (1, 2, 3...)
    - Also track which DB each concept belongs to

    Returns:
    - content_to_system: { "P1": "1" }
    - system_to_content: { "1": "P1" }
    - system_to_db: { "1": "python_learning.db" }
    """

    conn = sqlite3.connect(tutor_db)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT system_concept_id, content_concept_id, source_db
        FROM concept_id_map
    """)

    content_to_system = {}
    system_to_content = {}
    system_to_db = {}

    for sys_id, content_id, db in cursor.fetchall():
        sys_id = str(sys_id)
        content_id = str(content_id)

        content_to_system[content_id] = sys_id
        system_to_content[sys_id] = content_id
        system_to_db[sys_id] = db

    conn.close()
    return content_to_system, system_to_content, system_to_db


# =========================================================
# 2. LOAD GRAPH (CONVERT TO SYSTEM SPACE)
# =========================================================
def load_graph(db_paths: List[str], content_to_system: Dict[str, str]):
    """
    Loads all concepts + dependencies from subject DBs
    and converts them into system_concept_id space.

    Example:
    P2 depends on P1 → becomes → 2 depends on 1

    Returns:
    - concepts: set of system IDs
    - reverse_adj: { concept: [prerequisites] }
    """

    concepts = set()
    reverse_adj = defaultdict(list)

    for db_path in db_paths:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # ---- Load concepts ----
        cursor.execute("SELECT concept_id FROM concepts")

        for (cid,) in cursor.fetchall():
            if cid in content_to_system:
                concepts.add(content_to_system[cid])

        # ---- Load dependencies ----
        try:
            cursor.execute("""
                SELECT concept_id, prerequisite_id
                FROM concept_dependencies
            """)

            for concept, prereq in cursor.fetchall():
                if concept in content_to_system and prereq in content_to_system:
                    c_sys = content_to_system[concept]
                    p_sys = content_to_system[prereq]

                    reverse_adj[c_sys].append(p_sys)

        except Exception:
            # If table doesn't exist → ignore
            pass

        conn.close()

    return concepts, reverse_adj


# =========================================================
# 3. LOAD MASTERY (FROM knowledge_state)
# =========================================================
def load_mastery(tutor_db: str, learner_id: str, content_to_system: Dict[str, str]):
    """
    Loads learner mastery from knowledge_state table.

    Converts:
    content_id (P1) → system_id (1)

    Returns:
    { "1": 0.8, "2": 0.5 }
    """

    conn = sqlite3.connect(tutor_db)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT state_json
        FROM knowledge_state
        WHERE student_id = ?
        ORDER BY updated_at DESC
        LIMIT 1
    """, (learner_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return {}

    import json
    try:
        data = json.loads(row[0])
        mastery_raw = data.get("mastery", {})
    except:
        return {}

    mastery = {}

    for cid, val in mastery_raw.items():
        cid = str(cid)

        if cid in content_to_system:
            mastery[content_to_system[cid]] = float(val)

    return mastery

# =========================================================
# 4. LOAD BEHAVIOUR (FROM behaviour_state)
# =========================================================
def load_behavior(tutor_db: str, learner_id: str):
    """
    Loads learner behavior (like struggling, anomaly score).

    Used to adjust difficulty later.

    Returns:
    {
        "behavior_score": 0.78,
        "label": "struggling"
    }
    """

    conn = sqlite3.connect(tutor_db)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT behavior_score, behavior_label
        FROM behaviour_state
        WHERE learner_id = ?
        ORDER BY timestamp DESC
        LIMIT 1
    """, (learner_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"behavior_score": 0.0, "label": "normal"}

    return {
        "behavior_score": float(row[0]),
        "label": row[1]
    }


# =========================================================
# 5. THRESHOLD CALCULATION
# =========================================================
def get_threshold(mastery: Dict[str, float]):
    """
    Adaptive threshold based on average mastery.

    Logic:
    - Weak student → easier threshold
    - Strong student → stricter threshold
    """

    if not mastery:
        return 0.6

    avg = sum(mastery.values()) / len(mastery)

    if avg < 0.3:
        return 0.5
    elif avg < 0.6:
        return 0.6
    else:
        return 0.7


# =========================================================
# 6. UNLOCK / BLOCK LOGIC
# =========================================================
def compute_unlocked_blocked(concepts, reverse_adj, mastery):
    """
    Core logic:

    A concept is:
    - UNLOCKED → if all prerequisites >= threshold
    - BLOCKED → if any prerequisite < threshold

    Returns:
    - unlocked list
    - blocked list with explanation
    """

    threshold = get_threshold(mastery)

    unlocked = []
    blocked = []

    for cid in concepts:

        prereqs = reverse_adj.get(cid, [])

        # No prereqs → always unlocked
        if not prereqs:
            unlocked.append(cid)
            continue

        failed = []
        prereq_mastery = {}

        for p in prereqs:
            m = mastery.get(p, 0.0)
            prereq_mastery[p] = m

            if m < threshold:
                failed.append(p)

        if not failed:
            unlocked.append(cid)
        else:
            blocked.append({
                "concept_id": cid,
                "blocked_by": failed,
                "prereq_mastery": prereq_mastery,
                "threshold": threshold
            })

    return unlocked, blocked, threshold


# =========================================================
# 7. MAIN PIPELINE FUNCTION
# =========================================================
def run_dependency_module(tutor_db, db_paths, learner_id):
    """
    FULL PIPELINE:

    1. Load mapping
    2. Build graph (system IDs)
    3. Load mastery
    4. Load behavior
    5. Compute unlocked/blocked

    Returns:
    - unlocked concepts
    - blocked concepts
    - threshold
    - behavior info
    """

    # Step 1: mapping
    content_to_system, _, _ = load_mapping(tutor_db)

    # Step 2: graph
    concepts, reverse_adj = load_graph(db_paths, content_to_system)

    # Step 3: mastery
    mastery = load_mastery(tutor_db, learner_id, content_to_system)

    # Step 4: behavior
    behavior = load_behavior(tutor_db, learner_id)

    # Step 5: compute
    unlocked, blocked, threshold = compute_unlocked_blocked(
        concepts, reverse_adj, mastery
    )

    return {
        "unlocked_concepts": unlocked,
        "blocked_concepts": blocked,
        "threshold": threshold,
        "behavior": behavior
    }


# =========================================================
# 8. TEST RUN
# =========================================================
if __name__ == "__main__":

    TUTOR_DB = "Updated_DB/tutor.db"

    DB_PATHS = [
        "Updated_DB/python_learning.db",
        "Updated_DB/database_sql.db",
        "Updated_DB/html_web_basics.db",
        "Updated_DB/git_version_control.db",
        "Updated_DB/data_structures.db",
    ]

    result = run_dependency_module(
        tutor_db=TUTOR_DB,
        db_paths=DB_PATHS,
        learner_id="14"
    )

    print("\nUnlocked:", result["unlocked_concepts"])
    print("\nBlocked:", result["blocked_concepts"])
    print("\nThreshold:", result["threshold"])
    print("\nBehavior:", result["behavior"])
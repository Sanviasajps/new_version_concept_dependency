# import sqlite3
# import os

# def get_concepts(subject):
#     db_map = {
#         "datastructures": "data_structures.db",
#         "sql": "database_sql.db",
#         "git": "git_version_control.db",
#         "html" : "html_web_basics.db",
#         "python": "python_learning.db"
#     }


import sqlite3

from concept_dependency import run_dependency_module

# def get_db(content_concept_id):
#     db = ''
#     if content_concept_id[0] == "D":
#         db = "data_structures.db"
#     elif content_concept_id[0] == "S":
#         db = "database_sql.db"
#     elif content_concept_id[0] == "G":
#         db = "git_version_control.db"
#     elif content_concept_id[0] == "H":
#         db = "html_web_basics.db"
#     elif content_concept_id[0] == "P":
#         db = "python_learning.db"
#     else:
#         print("INVALID CONTENT_CONCEPT_ID")
#         exit(1)
#     json_mapping["source_db"] = db

def get_concept_details(db_path, concept_id):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        query = """
        SELECT name, difficulty, description
        FROM concepts
        WHERE concept_id = ?
        """

        cursor.execute(query, (concept_id,))
        row = cursor.fetchone()

        conn.close()

        if row:
            json_mapping["concept_name"] = row[0]
            json_mapping["difficulty"] = row[1]
            json_mapping["description"] = row[2]
        else:
            for key in json_mapping:
                json_mapping[key] = "None"
            json_mapping['status'] = "Failed"

    except Exception as e:
        return {"error": str(e)}

def get_content_concept_id_and_domain_and_db(db_path,system_concept_id):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        query = """
        Select content_concept_id,domain,source_db from concept_id_map
        where system_concept_id = ?
        """
        
        cursor.execute(query, (system_concept_id,))
        row = cursor.fetchone()

        if not row:
            for key in json_mapping:
                json_mapping[key] = "None"
            json_mapping['status'] = "Failed"
            return

        conn.close()

        json_mapping["content_concept_id"] = row[0]
        json_mapping["domain"] = row[1]
        json_mapping["source_db"] = row[2]

    except Exception as e:
        print(f"Error fetcing content_concept_id {e}")


# json_mapping["system_concept_id"] = input("Enter the System Concept ID : ")

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

for concept in result["unlocked_concepts"]:
    json_mapping = {
        "system_concept_id" : "",
        "content_concept_id" : "",
        "domain":"",
        "concept_name" : "",
        "description" : "",
        # "teaching_strategy" : "",
        "difficulty" : "",
        # "content_type" : "",
        # "instruction" : "",
        "source_db" : "",
        "status": "" 
    }
    
    json_mapping["system_concept_id"] = concept
    get_content_concept_id_and_domain_and_db(f"Updated_DB/tutor.db",json_mapping["system_concept_id"])

    get_concept_details(f"Updated_DB/{json_mapping['source_db']}", json_mapping['content_concept_id'])
        
    if json_mapping["status"] != "Failed":
        json_mapping["status"] = "Success"

    print("======================================")
    for key in json_mapping:
        print(f"{key} : {json_mapping[key]}")


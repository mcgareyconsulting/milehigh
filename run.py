# from app.test import get_trello_identifiers
# from app.sheets import get_onedrive_identifiers

# # Main entry point for the script
# if __name__ == "__main__":
#     # Step 1: Get identifiers from Trello
#     print("Fetching identifiers from Trello...")
#     trello_identifiers = get_trello_identifiers()
#     print(f"Found {len(trello_identifiers)} Trello identifiers.")

#     # Step 2: Get identifiers from OneDrive
#     print("Fetching identifiers from OneDrive...")
#     onedrive_identifiers = get_onedrive_identifiers()
#     print(f"Found {len(onedrive_identifiers)} OneDrive identifiers.")

#     # Step 3: Compare identifiers
#     print("Comparing identifiers...")
#     matching_identifiers = set(trello_identifiers).intersection(
#         set(onedrive_identifiers)
#     )

#     print(f"Found {len(matching_identifiers)} matching identifiers:")
#     for identifier in matching_identifiers:
#         print(f"- {identifier}")

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port="8000")

import re
import argparse
import csv
import datetime

from mountains.db import connection
from mountains.models.kit import (
    KitGroup,
    KitItem,
    kit_item_repo,
    kit_details_repo,
    KitDetail,
)


parser = argparse.ArgumentParser()
parser.add_argument("kit_csv", help="Exported CSV from master inventory")
parser.add_argument("target_db", help="SQL DB to target")

args = parser.parse_args()

kit_items = []

with open(args.kit_csv, "r") as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        kit_items.append(row)

print(kit_items[0].keys())

print(set(k["Type"] for k in kit_items))

with connection(args.target_db, locked=True) as conn:
    repo = kit_item_repo(conn)
    notes_repo = kit_details_repo(conn)
    print("Dropping and recreating table...")
    repo.drop_table()
    repo.create_table()
    notes_repo.drop_table()
    notes_repo.create_table()
    print(f"Inserting {len(kit_items)} kit items..")
    for row in kit_items:
        try:
            purchased_on = datetime.datetime.strptime(row["Purchased On"], "%d/%m/%Y")
        except ValueError:
            purchased_on = datetime.date(2000, 1, 1)

        if row["Purchase Price"]:
            purchase_price = float(row["Purchase Price"].lstrip("£"))
        else:
            purchase_price = 0.00

        if re.match(r"B[0-9]+", row["ID"]):
            kit_group = KitGroup.BOOKS
        elif re.match(r"H[0-9]+", row["ID"]):
            kit_group = KitGroup.HELMETS
        elif re.match(r"M[0-9]+", row["ID"]):
            kit_group = KitGroup.MAPS
        elif re.match(r"GE[0-9]+", row["ID"]):
            kit_group = KitGroup.GENERAL
        elif re.match(r"WK[0-9]+", row["ID"]):
            kit_group = KitGroup.WINTER
        elif re.match(r"CE[0-9]+", row["ID"]):
            kit_group = KitGroup.CLIMBING
        else:
            raise Exception(f"Cannot match {row['ID']}!")

        new_item = KitItem(
            id=repo.next_id(),
            club_id=row["ID"],
            description=row["Description"],
            brand=row["Brand"],
            color=row["Color"],
            size="",
            kit_type=row["Type"],
            kit_group=kit_group,
            purchased_on=purchased_on,
            purchase_price=purchase_price,
        )
        repo.insert(new_item)

        if row["Last Condition"]:
            try:
                check_date = datetime.datetime.strptime(row["Last Checked"], "%d/%m/%Y")
            except ValueError:
                check_date = datetime.datetime.now()

            new_note = KitDetail(
                id=notes_repo.next_id(),
                kit_id=new_item.id,
                # Megs id
                user_id=506,
                added_dt=check_date,
                condition=row["Last Condition"],
                note=row["Notes"] if row["Notes"] else None,
            )
            notes_repo.insert(new_note)

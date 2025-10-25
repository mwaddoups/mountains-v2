import datetime
import csv
import argparse
from mountains.models.kit import KitGroup, KitGroup, KitItem, kit_item_repo
from mountains.db import connection

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

with connection(args.target_db, locked=True) as conn:
    repo = kit_item_repo(conn)
    print('Dropping and recreating table...')
    repo.drop_table()
    repo.create_table()
    print(f'Inserting {len(kit_items)} kit items..')
    for row in kit_items:
        try:
            purchased_on=datetime.datetime.strptime(row['Purchased On'], '%d/%m/%Y')
        except ValueError:
            purchased_on = datetime.date(2000, 1, 1)

        if row['Purchase Price']:
            purchase_price = float(row['Purchase Price'].lstrip('£'))
        else:
            purchase_price = 0.00

        new_item = KitItem(
            id=repo.next_id(),
            club_id=row['ID'],
            description=row['Description'],
            brand=row['Brand'],
            color=row['Color'],
            size='',
            kit_type=row['Type'],
            # TODO: Set this correctly
            kit_group=KitGroup.GENERAL,
            purchased_on=purchased_on,
            purchase_price=purchase_price,
        )
        repo.insert(new_item)

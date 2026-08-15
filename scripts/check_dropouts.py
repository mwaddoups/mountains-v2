import itertools
import sqlite3

num_removed = """
    SELECT users.first_name, users.last_name, COUNT(events.title) as num_dropouts 
    FROM activity 
    INNER JOIN events ON activity.event_id = events.id  
    INNER JOIN users on ('removed ' || users.first_name || ' ' || users.last_name || ' from')  = activity.action 
    WHERE (abs(julianday(activity.dt) - julianday(events.event_dt)) < 2.0
        OR activity.dt >= events.event_dt)
    AND (activity.action LIKE 'removed%') 
    AND events.event_type IN (1,2,3,4,6,7) 
    AND events.event_dt > '2026-01-01' 
    GROUP BY users.first_name, users.last_name
    ORDER BY num_dropouts;
"""

num_left = """
SELECT users.first_name, users.last_name, COUNT(events.title) AS num_dropouts 
FROM activity 
INNER JOIN events ON activity.event_id = events.id  
INNER JOIN users on users.id = activity.user_id 
WHERE (abs(julianday(activity.dt) - julianday(events.event_dt)) < 2.0
    OR activity.dt >= events.event_dt)
AND (activity.action = 'left') 
AND events.event_type IN (1,2,3,4,6,7) 
AND events.event_dt > '2026-01-01' 
GROUP BY users.first_name, users.last_name
ORDER BY num_dropouts;
"""

conn = sqlite3.connect("test.db")

removed = conn.execute(num_removed).fetchall()
left = conn.execute(num_left).fetchall()

data = {}

for r in itertools.chain(removed, left):
    name = r[0] + " " + r[1]
    if name not in data:
        data[name] = 0
    data[name] += r[2]

for i, rec in enumerate(sorted(data.items(), key=lambda x: x[1], reverse=True)[:10]):
    print(f"{i + 1}. {rec[0]} - {rec[1]} dropouts")

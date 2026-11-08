--- check the clean file ---
OK — 1 file(s) checked, no duplicate keys.
--- check the file with duplicates ---
FAIL examples/duplicates.json:3: duplicate key 'name' in object $
FAIL examples/duplicates.json:7: duplicate key 'port' in object $.server
FAIL examples/duplicates.json:12: duplicate key 'id' in object $.items[0]
Checked 1 file(s), 3 problem(s) in 1 file(s).
--- check the whole examples folder ---
FAIL examples/duplicates.json:3: duplicate key 'name' in object $
FAIL examples/duplicates.json:7: duplicate key 'port' in object $.server
FAIL examples/duplicates.json:12: duplicate key 'id' in object $.items[0]
FAIL examples/configs/app.json:3: duplicate key 'debug' in object $
Checked 3 file(s), 4 problem(s) in 2 file(s).

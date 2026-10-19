# WhatsApp test chats: TEST DATA ONLY

Every file in this folder is **made up** for the unit tests. The names, phone numbers, addresses
and orders are invented; they are not real people or real conversations. Do not put a real chat
here.

| File | What it checks |
|---|---|
| `TESTDATA_android_12h.txt` | Android, 12 hour clock with am/pm, day/month/year, a multi-line message, system lines, media |
| `TESTDATA_android_24h.txt` | Android, 24 hour clock, two orders from two customers, an order spread over several messages |
| `TESTDATA_iphone.txt` | iPhone layout `[date, time] Name: text`, with seconds and invisible marks |
| `TESTDATA_month_first.txt` | month/day/year (a day above 12 in the second place) |
| `TESTDATA_ambiguous.txt` | every date is 12 or below, so day-first and month-first both fit |
| `TESTDATA_group.txt` | a group chat with several customers |

Each file starts with a line that is not a message; the parser must ignore it.

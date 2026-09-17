# Extra BGA accounts for `scrape_raw_replay.py --rotate-accounts`.
# Copy to accounts.py (gitignored) and fill in. When BGA's daily replay limit
# is hit on one account, the scraper logs in with the next.
ACCOUNTS = [
    ("first_account@example.com",  "password1"),
    ("second_account@example.com", "password2"),
]

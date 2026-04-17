# EPS Validation — Cloud Routine

Automated EPS postage validation for USPS mailing reports.

## What It Does

- Reads the latest USPS mailing CSV from Google Drive
- Validates against rate rules, permit requirements, and transaction types
- Flags billing discrepancies (zero pieces, out-of-range rates, missing IDs)
- Saves a corrections CSV back to Google Drive

## Files

| File | Purpose |
|------|---------|
| `eps_validator.py` | Core validation logic |
| `eps_config.txt` | Rate rules and permit config (lives on Google Drive, not in repo) |

## Usage

### As a Claude Code routine:
The routine runs `eps_validator.py` against the latest CSV on Google Drive and reports results.

### Locally:
```bash
python3 eps_validator.py --data-dir /path/to/eps-reports
```

## Config

The validator reads `eps_config.txt` from the data directory. This file contains:
- Rate table (permit | class | low | high)
- Permits requiring customer reference IDs
- USPS credentials (standalone app only — not used by the routine)

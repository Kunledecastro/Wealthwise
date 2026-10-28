# Sample statements (synthetic)

These files contain **made-up data** for testing imports. They are shaped like common bank
exports (preamble lines, separate debit/credit columns, newest-first order) but are not copied
from any bank.

| File | What it tests |
|---|---|
| `sample-gtbank-style-statement.csv` | 9 rows, ₦100,000.00 → ₦423,943.06. Fees, a reversal, identical twin charges, a transfer out, masked account/card numbers |
| `sample-wallet-statement.xlsx` | The same transactions as an Excel "Money In / Money Out" wallet export (re-importing it into the same account finds all 9 as already imported) |
| `sample-kuda-transfer-in.csv` | The receiving side of the ₦100,000 transfer: imported into a second account it is matched as a transfer |
| `sample-unusual-headers.csv` | Headers Wealthwise can't recognise, so you choose the columns yourself (and it remembers) |

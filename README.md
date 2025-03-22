# home-finance
Interact with a local DB to track financial transactions.

OFX files are obtained from financial institutions, converted to JSON files for processing with this library using Jupyter lab.
The models consist of Transaction, Category, and ExternalAccount, to respectively store the transactions, the spending/income categorization and the account it took place in.
Transactions can represent transfers between ExternalAccounts or can be just associated with a category.

The interactive package has methods suited to be used during a Juptyer lab session to interactively work with existing data, add new entries by hand, or load from a file.

Example notebook:
```
from home_finance.interactive.prompt import load_transactions, get_account_by_name, current_balance, new_transaction, recent_transactions, search, new_from_search

checking = get_account_by_name('Patelco Checking')
# look at some recent transactions
recent_transactions(checking, count=20)

# interactively load transactions from a JSON file
load_transactions(checking, f'/tmp/2025-03-22/Credit Union:CHECKING:123456.json')

```



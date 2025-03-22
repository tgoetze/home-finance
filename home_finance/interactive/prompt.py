from colored import fg, bg, stylize
from datetime import datetime
import json
from django.db.models import Sum
from django.db.models.manager import Manager
from .util import moneyfmt
from home_finance.components.category.models import Category
from home_finance.components.external_account.models import ExternalAccount
from home_finance.components.transaction.models import Transaction, date_from_string, findTransactions, next_number, search_txn, transaction_from_template


def current_balance(account: ExternalAccount):
    print(
        f'Current balance on account {account.name} is:\t\t\t\t {amount_style(current_account_balance(account, as_string=False))}')


def load_transactions(to_account: ExternalAccount, filename: str):
    """
    Interactively walk through each provided transaction and help the user decide on the action to take.

    TODO:
    Now there is a transaction_id field that can be used to know 2 similar entries during a since file processing
    run are not the same. When two of same amounts for the same description occur, often times the "findTransactions"
    finds a single one both times and so one of them is ignored.

    Idea: keep track of transaction_id and which ones were processed, so if/when you see (in the input file) a similar
    transaction, know that it should *not* match the previous one. A challenge is that the findTransactions does not
    know the transaction_id (and it should not store it since institutions (like CitiBank) change the id values from
    download to download (seems they stabilize on final statement, but for pre-finalized statements they vary).
    """
    with open(filename) as f:
        transactions = json.load(f)

    print(f'Found {len(transactions)} in the file: {filename}')
    # tell user the balance after before we start
    print(f'Starting balance on account {to_account.name} is:\t\t\t\t {amount_style(current_account_balance(to_account, as_string=False))}')

    matched_pks = set()
    for txn in transactions:
        (candidate_txn, possibles) = findTransactions(to_account, txn, matched_pks)
        if len(possibles) > 0:
            print(f'Possible matches of: {date_style(candidate_txn.date)}: {amount_style(candidate_txn.amount)}, {candidate_txn.description}')
            for i, possible in enumerate(possibles):
                print(f'\t{i}: {date_style(possible.date)}: {possible.num if possible.num else "   "} {possible.amount}, {possible.description}\n'
                      f'\t\tCategory: {possible.category.name if possible.category else "None"},'
                      f'\t\tTransfer account: {possible.transfer_account.name if possible.transfer_account else "None"},'
                      f'\t\tReconciled: {possible.reconciled}')
            # For already reconciled we insist same date, since assume it was loaded originally from a file,
            # so dates will match, unless it has a num, since that is good enough to ensure matching
            if len(possibles) == 1 and possibles[0].reconciled and ((possibles[0].num and len(possibles[0].num) > 0) or
                                                                    possibles[0].date == date_from_string(txn['date'])):
                print(f'Above transaction was found and is reconciled, so no action being provided.')
                matched_pks.add(possibles[0].id)
            else:
                handled = False
                while not handled:
                    prompt_input = input(f'If this transaction {candidate_txn.description}:{amount_style(candidate_txn.amount)} appears above and you are happy with it, input "s".'
                                         f'To reconcile or ignore a transaction from the list type: "r<num>" or "i<num>".'
                                         f'To add a new transaction input "n".'
                                         f'To search for a template enter "t".')
                    if prompt_input.startswith('n'):
                        handled = do_new_transaction(candidate_txn, handled, matched_pks)
                    if prompt_input.startswith('t'):
                        handled = do_search_on_input(handled, matched_pks, to_account, txn)
                    if prompt_input.startswith('s'):
                        print(f'Skipping transaction: {date_style(candidate_txn.date)}: {amount_style(candidate_txn.amount)}, {candidate_txn.description}')
                        handled = True
                    if prompt_input.startswith('r') or prompt_input.startswith('i'):
                        transaction_index = int(prompt_input[1:])
                        if transaction_index < 0 or transaction_index >= len(possibles):
                            print(f'Cannot reconcile or ignore item number: {transaction_index} since it is outside of the range')
                        else:
                            if prompt_input.startswith('r'):
                                possibles[transaction_index].reconciled = True
                                possibles[transaction_index].save()
                                print(f'Reconciled transaction.')
                            else:
                                print(f'Ignored transaction.')
                            handled = True
                            matched_pks.add(possibles[transaction_index].id)
        else:
            handled_txn = False
            while not handled_txn:
                print(f'No matching transactions found. {date_style(candidate_txn.date)}: {amount_style(candidate_txn.amount)}, {candidate_txn.description}')
                add_new = input(f'Input "n" to create a new one from scratch.'
                                f'"s" to search for a template, '
                                f'"m" to automatically search for the exact description, or anything else to skip.')
                if add_new == 'n' or add_new == 'N':
                    handled_txn = do_new_transaction(candidate_txn, handled_txn, matched_pks)
                elif add_new == 's' or add_new == 'S':
                    handled_txn = do_search_on_input(handled_txn, matched_pks, to_account, txn)
                elif add_new == 'm' or add_new == 'M':
                    handled_txn = do_search_on_input(handled_txn, matched_pks, to_account, txn, search_phrase=txn['payee'])
                elif add_new.startswith('s'):
                    handled_txn = do_search_on_input(handled_txn, matched_pks, to_account, txn,
                                                     search_phrase=add_new[1:].strip())
                else:
                    print(f'Ignoring transaction')
                    handled_txn = True


def do_search_on_input(handled_txn, matched_pks, to_account, txn, search_phrase=None):
    if search_phrase:
        search_input = search_phrase
    else:
        search_input = input(f'Search criteria for a template transaction: ')
    if len(search_input) > 2:
        template = search(search_input)
        if template:
            new_txn = transaction_from_template(template, txn)
            new_txn.account = to_account
            prompt_for_string_change(new_txn, 'notes')
            new_txn.save()
            handled_txn = True
            matched_pks.add(new_txn.id)
            print(f'Saved transaction in amount: {amount_style(new_txn.amount)}')
            print(
                f'New balance on account {new_txn.account.name} is:\t\t\t\t {amount_style(current_account_balance(new_txn.account, as_string=False))}')
    else:
        print('Please type more than 2 characters when searching for a template')
    return handled_txn


def do_new_transaction(new_txn, handled_txn, matched_pks):
    category, transfer_account = prompt_for_category_or_transfer_account()
    new_txn.category = category
    new_txn.transfer_account = transfer_account
    cleared = input(f'This transaction will be set as reconciled, type: "no" to change that.')
    new_txn.reconciled = False if cleared.upper() == 'NO' else True
    new_description = input(f'Type a new description (or just enter to skip): {new_txn.description}')
    if len(new_description) > 1:
        new_txn.description = new_description
    new_notes = input(f'Type notes to add, or enter to skip')
    if len(new_notes) > 1:
        new_txn.notes = new_notes
    new_txn.save()
    handled_txn = True
    matched_pks.add(new_txn.id)
    print(
        f'New balance on account {new_txn.account.name} is:\t\t\t\t {amount_style(current_account_balance(new_txn.account, as_string=False))}')
    return handled_txn


def new_transaction(transaction_date: str, amount: float, description: str, notes: str = None,
                    account: ExternalAccount = None, category: Category = None, num: str = None):
    """
    Walk through creating a new transaction for a user.
    """
    transaction_date = transaction_date.replace('/', '-')
    t_date = date_from_string(transaction_date)
    transaction = Transaction(date=t_date, amount=amount, description=description, notes=notes, num=num,
                              account=account, category=category)
    transfer_transaction = None
    if not account:
        transaction.account = prompt_for_account()
    if not category:
        transaction.category = prompt_for_category()
    # When creating a manual transaction, a transfer should appear in both accounts, but during import only one,
    # since it will be imported on each account individually
    transfer_account = prompt_for_account(is_transfer=True)
    if not notes:
        notes = input('Input any notes for this transaction: ')
    transaction.notes = notes
    if transfer_account:
        transaction.transfer_account = transfer_account
        transfer_transaction = Transaction(date=t_date, amount=-1.0*amount, description=description, notes=notes,
                                           account=transfer_account, transfer_account=transaction.account,
                                           category=transaction.category)
    transaction.save()
    if transfer_transaction:
        transfer_transaction.save()
    # tell user the balance after this transaction has been saved
    print(f'New balance on account {transaction.account.name} is:\t\t\t\t {amount_style(current_account_balance(transaction.account, as_string=False))}')
        

def prompt_for_category_or_transfer_account():
    """
    Get input and help user find a category or transfer account to be used
    """
    category = prompt_for_category()
    transfer_account = prompt_for_account(is_transfer=True)
    return category, transfer_account


def prompt_for_category():
    """
    Prompt for an category
    """
    return prompt_by_name('category', Category.objects)


def prompt_for_account(is_transfer: bool = False):
    """
    Prompt for an account
    """
    acct = prompt_by_name(f'{"transfer " if is_transfer else ""}account', ExternalAccount.objects)
    if acct:
        current_balance(acct)
    return acct


def get_account_by_name(acct_name: str):
    items = ExternalAccount.objects.filter(name=acct_name).all()
    if len(items) != 1:
        print(f'Found {len(items)} accounts matching the name: {acct_name}')
    else:
        current_balance(items[0])
        return items[0]


def prompt_by_name(object_name: str, objects: Manager):
    """
    Prompt for an item by name
    """
    item = None
    handled = False
    while not handled:
        item_query = input(f'Input the name of an {object_name} to find, or "none" to skip {object_name} lookup: ')
        if item_query.upper() == 'NONE':
            handled = True
        else:
            possible_items = objects.filter(name__contains=item_query).all()
            for i, possible in enumerate(possible_items):
                print(f'\t{i}: {possible.name}')
            select_item = input(f'Which {object_name} number do you want to select, or "none" to skip: ')
            if select_item.upper() == 'NONE':
                handled = True
            else:
                try:
                    select_index = int(select_item)
                    if select_index < 0 or select_index > len(possible_items):
                        print(f'Input provided is out of range.')
                    else:
                        item = possible_items[select_index]
                        handled = True
                except ValueError:
                    print(f'Failed to parse input as an integer.')
    return item


def search(input_query: str):
    """
    Search transactions and return a candidate that was selected
    """
    item = None
    handled = False
    possible_items = search_txn(input_query)
    while not handled:
        for i, possible in enumerate(possible_items):
            print(
                f'{i}: {date_style(possible.date)}: {possible.num if possible.num else "    "} {possible.amount}, {possible.description}, {possible.notes}\n'
                f'\tCategory: {possible.category.name if possible.category else "None"},'
                f'\tAccount: {possible.account.name if possible.account else "None"},'
                f'\tTransfer account: {possible.transfer_account.name if possible.transfer_account else "None"},'
                f'\tReconciled: {possible.reconciled}')
        select_item = input(f'Which transaction number do you want to select, or "none" to skip and retry: ')
        if select_item.upper() == 'NONE':
            handled = True
        else:
            try:
                select_index = int(select_item)
                if select_index < 0 or select_index > len(possible_items):
                    print(f'Input provided is out of range.')
                else:
                    item = possible_items[select_index]
                    handled = True
            except ValueError:
                print(f'Failed to parse input as an integer.')
    return item


def new_from_search(input_query: str):
    """
    Search for transactions in order to create a new one from a search result
    """
    template = search(input_query)
    if not template:
        print('No matched transaction found to use as a template')
        return
    today = datetime.today()
    t_date = date_from_string(f'{today:%Y-%m-%d}')
    transaction = Transaction(date=t_date, amount=template.amount, description=template.description,
                              notes=template.notes, num='', account=template.account, category=template.category,
                              transfer_account=template.transfer_account)
    handled = False
    if transaction.account and template.num:
        transaction.num = next_number(transaction.account)
    while not handled:
        new_date = input(f'New date: {transaction.date:%Y-%m-%d}: ')
        if new_date:
            transaction.date = date_from_string(new_date)
        new_amount = input(f'New amount: {transaction.amount}: ')
        if new_amount:
            try:
                transaction.amount = float(new_amount)
            except ValueError:
                print('Invalid amount, please try again.')
                continue
        prompt_for_string_change(transaction, 'description')
        prompt_for_string_change(transaction, 'notes')
        prompt_for_string_change(transaction, 'num')
        accept_account = input(f'Keep account {transaction.account.name} [Y|n]:')
        if accept_account and accept_account.startswith('n'):
            new_account = prompt_for_account(False)
            if new_account:
                transaction.account = new_account
        if transaction.category:
            accept_category = input(f'Keep category {transaction.category.name} [Y|n]:')
            if accept_category and accept_category.startswith('n'):
                new_category = prompt_for_category()
                if new_category:
                    transaction.category = new_category
        if transaction.transfer_account:
            accept_transfer_account = input(f'Keep transfer_account {transaction.transfer_account.name} [Y|n]:')
            if accept_transfer_account and accept_transfer_account.startswith('n'):
                new_transfer_account = prompt_for_account(False)
                if new_transfer_account:
                    transaction.transfer_account = new_transfer_account
        reconciled = input(f'Make it reconciled [N|y]:')
        if reconciled and reconciled.startswith('y'):
            transaction.reconciled = True
        accept = input(
            f'Accept: {date_style(transaction.date)}: {transaction.num if transaction.num else "    "} {transaction.amount}, {transaction.description}, {transaction.notes}\n'
            f'\tCategory: {transaction.category.name if transaction.category else "None"},'
            f'\tAccount: {transaction.account.name if transaction.account else "None"},'
            f'\tTransfer account: {transaction.transfer_account.name if transaction.transfer_account else "None"},'
            f'\tReconciled: {transaction.reconciled}: [Y|n|q]')
        if accept and accept.startswith('q'):
            handled = True
        elif not accept or (accept.startswith('Y') or accept.startswith('y')):
            transaction.save()
            print(f'New balance on account {transaction.account.name} is:\t\t\t\t {amount_style(current_account_balance(transaction.account, as_string=False))}')
            handled = True


def prompt_for_string_change(transaction: Transaction, field_name: str):
    """Prompt for potentially changing a field value"""
    new_value = input(f'New {field_name}, ({getattr(transaction, field_name)}): ')
    if new_value:
        if len(new_value) == 0 or new_value.upper() == 'NONE':
            setattr(transaction, field_name, None)
        else:
            setattr(transaction, field_name, new_value)


def current_account_balance(account: ExternalAccount, as_string=True):
    """Get the current balance from the account as either a printable string or numeric
    TODO: support date argument to support ignoring future dates, so I can get today's current balance ignoring pending bills
    """
    balance = Transaction.objects.filter(account=account, parent__isnull=True).aggregate(Sum('amount')).get('amount__sum')
    if as_string:
        return moneyfmt(balance)
    else:
        return balance


def recent_transactions(account: ExternalAccount, count=10):
    """Print some of the most recent transactions from this account"""
    balance = current_account_balance(account, as_string=False)
    txns = Transaction.objects.filter(account=account).order_by('-date', '-num', '-id')[:count]
    for txn in txns:
        print(f'{date_style(txn.date)}: {txn.num if txn.num else "    "} {money_style(balance)} {money_style(txn.amount)}, {txn.description}, {txn.notes}\n'
              f'\tCategory: {txn.category.name if txn.category else "None"},'
              f'\tTransfer account: {txn.transfer_account.name if txn.transfer_account else "None"},'
              f'\tReconciled: {txn.reconciled}')
        balance = balance - txn.amount


def money_style(amount):
    if amount < 0:
        return stylize(moneyfmt(amount), bg("red"), fg("black"))
    return stylize(moneyfmt(amount), bg("green"), fg("white"))


def amount_style(amount):
    if amount < 0.0:
        return stylize(amount, bg("red"), fg("black"))
    return stylize(amount, bg("green"), fg("white"))

def date_style(d):
    return stylize(f'{d:%Y-%m-%d(%a)}', bg("blue"), fg("white"))

import os
import csv
import random
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session
import pandas as pd
import bcrypt

app = Flask(__name__)
app.secret_key = "super_secret_banking_key"  # Required for session management

ACCOUNTS_FILE = "accounts.csv"
TRANSACTIONS_FILE = "transactions.csv"

def init_files():
    if not os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["AccountNumber", "Name", "PinHash", "Balance"])
    if not os.path.exists(TRANSACTIONS_FILE):
        with open(TRANSACTIONS_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["AccountNumber", "DateTime", "Type", "Amount", "BalanceAfter"])

init_files()

def load_accounts():
    init_files()
    if os.path.getsize(ACCOUNTS_FILE) == 0:
        with open(ACCOUNTS_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["AccountNumber", "Name", "PinHash", "Balance"])
    return pd.read_csv(ACCOUNTS_FILE, dtype={"AccountNumber": str})


def load_transactions():
    init_files()
    if os.path.getsize(TRANSACTIONS_FILE) == 0:
        with open(TRANSACTIONS_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["AccountNumber", "DateTime", "Type", "Amount", "BalanceAfter"])
    return pd.read_csv(TRANSACTIONS_FILE, dtype={"AccountNumber": str})
def save_accounts(df):
    df.to_csv(ACCOUNTS_FILE, index=False)

def log_transaction(account_number, txn_type, amount, balance_after):
    with open(TRANSACTIONS_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            account_number,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            txn_type,
            round(amount, 2),
            round(balance_after, 2),
        ])

def generate_account_number():
    accounts = load_accounts()
    while True:
        number = str(random.randint(1000000000, 9999999999))
        if accounts.empty or number not in accounts["AccountNumber"].values:
            return number

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register", methods=["POST"])
def register():
    name = request.form.get("name").strip()
    pin = request.form.get("pin").strip()
    
    if not pin.isdigit() or len(pin) != 4:
        return render_template("index.html", error="PIN must be exactly 4 digits.")
    
    try:
        opening_balance = float(request.form.get("balance", 0))
        if opening_balance < 0:
            raise ValueError
    except ValueError:
        return render_template("index.html", error="Invalid opening deposit amount.")

    account_number = generate_account_number()
    pin_hash = bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()

    accounts = load_accounts()
    new_row = pd.DataFrame([[account_number, name, pin_hash, opening_balance]],
                           columns=["AccountNumber", "Name", "PinHash", "Balance"])
    accounts = pd.concat([accounts, new_row], ignore_index=True)
    save_accounts(accounts)

    if opening_balance > 0:
        log_transaction(account_number, "Opening Deposit", opening_balance, opening_balance)

    return render_template("index.html", success=f"Account created! Your Account Number is: {account_number}")

@app.route("/login", methods=["POST"])
def login():
    account_number = request.form.get("account_number").strip()
    pin = request.form.get("pin").strip()

    accounts = load_accounts()
    match = accounts[accounts["AccountNumber"] == account_number]

    if match.empty:
        return render_template("index.html", error="Account not found.")

    pin_hash = match.iloc[0]["PinHash"]
    if not bcrypt.checkpw(pin.encode(), pin_hash.encode()):
        return render_template("index.html", error="Incorrect PIN.")

    session["account_number"] = account_number
    return redirect(url_for("dashboard"))

@app.route("/dashboard")
def dashboard():
    if "account_number" not in session:
        return redirect(url_for("index"))
    
    acc_num = session["account_number"]
    accounts = load_accounts()
    row = accounts[accounts["AccountNumber"] == acc_num]
    name = row.iloc[0]["Name"]
    balance = float(row.iloc[0]["Balance"])

    transactions = load_transactions()
    history = transactions[transactions["AccountNumber"] == acc_num].to_dict(orient="records")

    return render_template("dashboard.html", name=name, account_number=acc_num, balance=balance, history=history)

@app.route("/transaction", methods=["POST"])
def transaction():
    if "account_number" not in session:
        return redirect(url_for("index"))

    acc_num = session["account_number"]
    action = request.form.get("action")
    
    accounts = load_accounts()
    balance = float(accounts.loc[accounts["AccountNumber"] == acc_num, "Balance"].iloc[0])

    if action in ["deposit", "withdraw"]:
        try:
            amount = float(request.form.get("amount"))
            if amount <= 0: raise ValueError
        except ValueError:
            return redirect(url_for("dashboard"))

        if action == "deposit":
            new_balance = balance + amount
            log_transaction(acc_num, "Deposit", amount, new_balance)
        else:
            if amount > balance:
                return redirect(url_for("dashboard"))
            new_balance = balance - amount
            log_transaction(acc_num, "Withdrawal", amount, new_balance)

        accounts.loc[accounts["AccountNumber"] == acc_num, "Balance"] = new_balance
        save_accounts(accounts)

    elif action == "transfer":
        target = request.form.get("target").strip()
        try:
            amount = float(request.form.get("amount"))
            if amount <= 0: raise ValueError
        except ValueError:
            return redirect(url_for("dashboard"))

        if target not in accounts["AccountNumber"].values or target == acc_num or amount > balance:
            return redirect(url_for("dashboard"))

        sender_new_balance = balance - amount
        receiver_new_balance = float(accounts.loc[accounts["AccountNumber"] == target, "Balance"].iloc[0]) + amount

        accounts.loc[accounts["AccountNumber"] == acc_num, "Balance"] = sender_new_balance
        accounts.loc[accounts["AccountNumber"] == target, "Balance"] = receiver_new_balance
        save_accounts(accounts)

        log_transaction(acc_num, f"Transfer to {target}", amount, sender_new_balance)
        log_transaction(target, f"Transfer from {acc_num}", amount, receiver_new_balance)

    return redirect(url_for("dashboard"))

@app.route("/logout")
def logout():
    session.pop("account_number", None)
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)
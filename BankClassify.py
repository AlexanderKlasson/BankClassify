import re
import dateutil
import os
from datetime import datetime

import pandas as pd
from textblob.classifiers import NaiveBayesClassifier
from colorama import init, Fore, Style
from tabulate import tabulate


def _replace_phonenumbers(df):
    """Read phonebook and swap numbers to names if possible (useful for swish)"""

    try:
        phonebook = pd.read_csv('contacts.csv', skiprows=0)
    except:
        print('No contacts.csv file exists or error reading file')
        return

    # Clean the numbers field from symbols and whitespace
    phonebook['Phone 1 - Value'] = phonebook['Phone 1 - Value'].str.replace('[+, ,-]','', regex=True)
    # Remove second number in special cases
    phonebook['Phone 1 - Value'] = phonebook['Phone 1 - Value'].str.split(':::').str[0]

    # Remove first 0 to get more similar to the  format +46 format as in swish
    phonebook['Phone 1 - Value'] = phonebook['Phone 1 - Value'].str.lstrip('046')

    #Remove 46 in all numbers that start with 46
    df['desc'] = df['desc'].str.replace(r'^46', '', regex=True)

    phonebook['Name'] = phonebook['Name'] + ' (Swish)'

    # Replace the desc if it matches the number in the phonebook
    phonebook_usable = phonebook[phonebook['Phone 1 - Value'].isin(df['desc'])][['Name', 'Phone 1 - Value']]
    phonebook_dictionary = phonebook.set_index('Phone 1 - Value')['Name'].to_dict()
    df['desc'] = df['desc'].replace(phonebook_dictionary)

    return df


def _print_transaction(row):
    print("On: %s\t %.0f SEK   Description: %s" % (row['date'], row['amount'], row['desc']))


def _strip_numbers(s):
#    """Strip numbers from the given string"""
#    return re.sub("[^A-Z ]", "", s)
    return s

class BankClassify():

    def __init__(self, data="AllData.csv"):
        """Load in the previous data (by default from `data`) and initialise the classifier"""

        # allows dynamic training data to be used (i.e many accounts in a loop)
        self.trainingDataFile = data

        if os.path.exists(data):
            self.prev_data = pd.read_csv(self.trainingDataFile)
        else:
            self.prev_data = pd.DataFrame(columns=['date', 'desc', 'amount', 'cat'])

        # TODO: Change the classifier to input more than just a tuple containing Class and description. "Date" and
        #  amount is not used atm. Weekday could also be interesting to add
        self.classifier = NaiveBayesClassifier(self._get_training(self.prev_data), self._extractor)

    def add_data(self, filename, bank="santander"):
        """Add new data and interactively classify it.

        Arguments:
         - filename: filename of Santander-format file
        """
        if bank == "santander":
            print("Adding Santander data!")
            self.new_data = self._read_santander_file(filename)
        elif bank == "nationwide":
            print("Adding Nationwide data!")
            self.new_data = self._read_nationwide_file(filename)
        elif bank == "lloyds":
            print("Adding Lloyds Bank data!")
            self.new_data = self._read_lloyds_csv(filename)
        elif bank == "barclays":
            print("Adding Barclays Bank data!")
            self.new_data = self._read_barclays_csv(filename)
        elif bank == "mint":
            print("Adding Mint data!")
            self.new_data = self._read_mint_csv(filename)
        elif bank == "SEB":
            print("Adding SEB data!")
            self.new_data = self._read_seb_xlsx(filename)

        _replace_phonenumbers(self.new_data)

        self._ask_with_guess(self.new_data)

        self.prev_data = pd.concat([self.prev_data, self.new_data])
        # save data to the same file we loaded earlier
        print("Saving additions to AllData.csv")
        self.prev_data.to_csv(self.trainingDataFile, index=False)

    def _prep_for_analysis(self):
        """Prepare data for analysis in pandas, setting index types and subsetting"""
        self.prev_data = self._make_date_index(self.prev_data)

        self.prev_data['cat'] = self.prev_data['cat'].str.strip()

        self.inc = self.prev_data[self.prev_data.amount > 0]
        self.out = self.prev_data[self.prev_data.amount < 0]
        self.out.amount = self.out.amount.abs()

        self.inc_noignore = self.inc[self.inc.cat != 'Ignore']
        self.inc_noexpignore = self.inc[(self.inc.cat != 'Ignore') & (self.inc.cat != 'Expenses')]

        self.out_noignore = self.out[self.out.cat != 'Ignore']
        self.out_noexpignore = self.out[(self.out.cat != 'Ignore') & (self.out.cat != 'Expenses')]

    def _read_categories(self):
        """Read list of categories from categories.txt"""
        categories = {}

        with open('categories.txt') as f:
            for i, line in enumerate(f.readlines()):
                categories[i] = line.strip()

        return categories

    def _add_new_category(self, category):
        """Add a new category to categories.txt"""
        with open('categories.txt', 'a') as f:
            f.write('\n' + category)

    def _ask_with_guess(self, df):
        """Interactively guess categories for each transaction in df, asking each time if the guess
        is correct"""
        # Initialise colorama
        init()

        df['cat'] = ""

        categories = self._read_categories()

        for index, row in df.iterrows():

            # Generate the category numbers table from the list of categories
            cats_list = [[idnum, cat] for idnum, cat in categories.items()]
            cats_table = tabulate(cats_list)

            stripped_text = _strip_numbers(row['desc'])

            # Guess a category using the classifier (only if there is data in the classifier)
            print("Coming up with a guess")
            if len(self.classifier.train_set) > 1:
                guess = self.classifier.classify(stripped_text)
            else:
                guess = ""


            # Print list of categories
            print(chr(27) + "[2J")
            print(cats_table)
            print("\n")
            # Print transaction
            _print_transaction(row)
            print(Fore.RED  + Style.BRIGHT + "My guess is: " + str(guess) + Fore.RESET + " (leave blank if correct, "
                "enter 'h' for help transactions and enter 'q' to quit)")

            input_value = input("> ")

            while input_value.lower() == 'h':
                print("On: %s\t %.0f SEK   Description: %s" % (row['date'], row['amount'], row['desc']))
                input_value = input("> ")

            # A Function to print prior and later transactions (for help) should be added

            if input_value.lower() == 'q':
                # If the input was 'q' then quit
                return df

            # Update classifier class
            if input_value == "":
                # If the input was blank then our guess was right!
                df.at[index, 'cat'] = guess
                self.classifier.update([(stripped_text, guess)])
            else:
                # Otherwise, our guess was wrong
                # There are 2 ways to enter an existing category, either matching the text or providing the number
                if input_value in categories.values():
                    category = input_value
                else:
                    try:
                        # Try converting the input to an integer category number
                        # If it works then we've entered a category
                        category_number = int(input_value)
                        category = categories[category_number]
                    except ValueError:
                        # Otherwise, we've entered a new category, so add it to the list of
                        # categories
                        category = input_value
                        self._add_new_category(category)
                    categories = self._read_categories()

                # Write correct answer
                df.at[index, 'cat'] = category
                # Update classifier
                self.classifier.update([(stripped_text, category)   ])

        return df

    def _make_date_index(self, df):
        """Make the index of df a Datetime index"""
        df.index = pd.DatetimeIndex(df.date.apply(dateutil.parser.parse, dayfirst=True))

        return df

    def _read_nationwide_file(self, filename):
        """Read a file in the csv file that Nationwide provides downloads in.

        Returns a pd.DataFrame with columns of 'date', 'desc' and 'amount'."""

        with open(filename) as f:
           lines = f.readlines()


        dates = []
        descs = []
        amounts = []

        for line in lines[5:]:

            line = "".join(i for i in line if ord(i)<128)
            if line.strip() == '':
                continue

            splits = line.split("\",\"")
            """
            0 = Date
            1 = Transaction type
            2 = Description
            3 = Paid Out
            4 = Paid In
            5 = Balance
            """
            date = splits[0].replace("\"", "").strip()
            date = datetime.strptime(date, '%d %b %Y').strftime('%d/%m/%Y')
            dates.append(date)

            # get spend/pay in amount
            if splits[3] != "": # paid out
                spend = float(re.sub("[^0-9\.-]", "", splits[3])) * -1
            else: # paid in
                spend = float(re.sub("[^0-9\.-]", "", splits[4]))

            amounts.append(spend)

            #Description
            descs.append(splits[2])

        df = pd.DataFrame({'date':dates, 'desc':descs, 'amount':amounts})

        df['amount'] = df.amount.astype(float)
        df['desc'] = df.desc.astype(str)
        df['date'] = df.date.astype(str)

        return df

    def _read_santander_file(self, filename):
        """Read a file in the plain text format that Santander provides downloads in.

        Returns a pd.DataFrame with columns of 'date', 'desc' and 'amount'."""
        with open(filename, errors='replace') as f:
            lines = f.readlines()

        dates = []
        descs = []
        amounts = []

        for line in lines[4:]:

            line = "".join(i for i in line if ord(i)<128)
            if line.strip() == '':
                continue

            splitted = line.split(":")

            category = splitted[0]
            data = ":".join(splitted[1:])

            if category == 'Date':
                dates.append(data.strip())
            elif category == 'Description':
                descs.append(data.strip())
            elif category == 'Amount':
                just_numbers = re.sub("[^0-9\.-]", "", data)
                amounts.append(just_numbers.strip())


        df = pd.DataFrame({'date':dates, 'desc':descs, 'amount':amounts})


        df['amount'] = df.amount.astype(float)
        df['desc'] = df.desc.astype(str)
        df['date'] = df.date.astype(str)

        return df

    def _read_lloyds_csv(self, filename):
        """Read a file in the CSV format that Lloyds Bank provides downloads in.

        Returns a pd.DataFrame with columns of 'date' 0 , 'desc'  4 and 'amount' 5 ."""

        df = pd.read_csv(filename, skiprows=0)

        """Rename columns """
        #df.columns = ['date', 'desc', 'amount']
        df.rename(
            columns={
                "Transaction Date" : 'date',
                "Transaction Description" : 'desc',
                "Debit Amount": 'amount',
                "Credit Amount": 'creditAmount'
            },
            inplace=True
        )

        # if its income we still want it in the amount col!
        # manually correct each using 2 cols to create 1 col with either + or - figure
        # lloyds outputs 2 cols, credit and debit, we want 1 col representing a +- figure
        for index, row in df.iterrows():
            if (row['amount'] > 0):
                # it's a negative amount because this is a spend
                df.at[index, 'amount'] = -row['amount']
            elif (row['creditAmount'] > 0):
                df.at[index, 'amount'] = row['creditAmount']

        # cast types to columns for math 
        df = df.astype({"desc": str, "date": str, "amount": float})

        return df

    def _read_mint_csv(self, filename) -> pd.DataFrame:
        """Read a file in the CSV format that mint.intuit.com provides downloads in.

        Returns a pd.DataFrame with columns of 'date', 'desc', and 'amount'."""

        df = pd.read_csv(filename, skiprows=0)

        """Rename columns """
        # df.columns = ['date', 'desc', 'amount']
        df.rename(
            columns={
                "Date": 'date',
                "Original Description": 'desc',
                "Amount": 'amount',
                "Transaction Type": 'type'
            },
            inplace=True
        )

        # mint outputs 2 cols, amount and type, we want 1 col representing a +- figure
        # manually correct amount based on transaction type colum with either + or - figure
        df.loc[df['type'] == 'debit', 'amount'] = -df['amount']

        # cast types to columns for math
        df = df.astype({"desc": str, "date": str, "amount": float})
        df = df[['date', 'desc', 'amount']]

        return df

    def _read_barclays_csv(self, filename):
            """Read a file in the CSV format that Barclays Bank provides downloads in.
            Edge case: foreign txn's sometimes causes more cols than it should
            Returns a pd.DataFrame with columns of 'date' 1 , 'desc' (memo)  5 and 'amount' 3 ."""

            # Edge case: Barclays foreign transaction memo sometimes contains a comma, which is bad.
            # Use a work-around to read only fixed col count
            # https://stackoverflow.com/questions/20154303/pandas-read-csv-expects-wrong-number-of-columns-with-ragged-csv-file
            # Prevents an error where some rows have more cols than they should
            temp=pd.read_csv(filename,sep='^',header=None,prefix='X',skiprows=1)
            temp2=temp.X0.str.split(',',expand=True)
            del temp['X0']
            df = pd.concat([temp,temp2],axis=1)

            """Rename columns """
            df.rename(
                columns={
                    1: 'date',
                    5 : 'desc',
                    3: 'amount'
                    },
                inplace=True
            )

            # cast types to columns for math
            df = df.astype({"desc": str, "date": str, "amount": float})

            return df


    def _read_seb_xlsx(self, filename):
        """Read a file in the xlsx format that SEB provides downloads in.

        Returns a pd.DataFrame with columns of 'date' 0 , 'desc'  4 and 'amount' 5 ."""

        df = pd.read_excel(filename, skiprows=7)

        """Rename columns """
        #df.columns = ['date', 'desc', 'amount']
        df.rename(
            columns={
                "Valutadatum" : 'date',
                "Text" : 'desc',
                "Belopp": 'amount',
            },
            inplace=True
        )

        # The actual transaction date is sometimes added to the "desc" field.
        # This is inserted into the "date" field and removed from the "desc" field
        df[['desc', 'date2']] = df['desc'].str.rsplit("/", n=1, expand=True)
        df['date2'].fillna(df['date'], inplace=True)
        df['date2'] = pd.to_datetime(df.date).dt.strftime('%d/%m/%Y')

        df.rename(columns={'date': 'date_old', 'date2': 'date'}, inplace=True)

        df['desc'] = df['desc'].str.rstrip(' ')
        # cast types to columns for math
        df = df.astype({"desc": str, "date": str, "amount": float})

        """
        del df['Bokföringsdatum']
        del df['date_old']
        del df['Verifikationsnummer']
        del df['Saldo']
        """
        print("Finished adding SEB data")

        return df

    def _get_training(self, df):
        """Get training data for the classifier, consisting of tuples of
        (text, category)"""
        train = []
        subset = df[df['cat'] != '']
        subset = subset.dropna()
        train_place = 0
        for i in subset.index:
            row = subset.iloc[train_place]
            new_desc = _strip_numbers(row['desc'])
            train.append( (new_desc, row['cat']) )
            train_place = train_place + 1

        return train

    def _extractor(self, doc):
        """Extract tokens from a given string"""
        # TODO: Extend to extract words within words
        # For example, MUSICROOM should give MUSIC and ROOM
        tokens = self._split_by_multiple_delims(doc, [' ', '/'])

        features = {}

        for token in tokens:
            if token == "":
                continue
            features[token] = True

        return features

    def _split_by_multiple_delims(self, string, delims):
        """Split the given string by the list of delimiters given"""
        regexp = "|".join(delims)

        return re.split(regexp, string)
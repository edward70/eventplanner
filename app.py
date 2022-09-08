# external libraries
from flask import * # import flask library to create webserver
from docx import Document # import docx library to process word document files

# builtin/local imports
import sqlite3, atexit, hashlib, datetime # import libraries for database, exit handling, hashing and dates & time
from functools import wraps # import decorator handler
from filters import nl2br # import jinja filter
from contextlib import contextmanager
import re

app = Flask(__name__) # create flask webserver
app.jinja_env.filters['nl2br'] = nl2br # enable newline to br converter plugin

# hardcoded constants
auth = {"username": "password"} # username -> password
names = {"username": "Example Teacher"} # username -> real name
# approval order removed since multiuser is outside of scope
#approval_order = ["username"]
# school calendar url
schoolcalendar = "https://docs.google.com/document/d/1IhUHiIH9ctDlDJ2-_vLI42qQm-MGW5-Yxxv0xx_8bQo/edit?usp=sharing"
# school activity calendar url
activitycalendar = "https://docs.google.com/document/d/e/2PACX-1vT12_PabQ-wKDFeGW26U1fAT9KhByozRazm7CJcLqHFqfB6cpGpRhHCmOWmIAZOSWpPbIvtqyNqvo8J/pub?embedded=true"
app.secret_key = "4Fa!R6w1@wkbMUSHO47r7#zmn" # key to encrypt user credentials in browser cookies

# disable thread checking since sqlite3 is thread safe, enable autocommit for faster writes -> database file for sqlite is data.db
con = sqlite3.connect('data.db', check_same_thread=False, isolation_level=None)
cur = con.cursor() # cursor for database access
cur.execute('PRAGMA journal_mode=WAL') # enable Write Ahead Logging for super speed
cur.execute('PRAGMA synchronous=NORMAL') # reduces syncing without corruption risk for WAL mode
cur.execute('PRAGMA auto_vacuum=FULL') # reduce db file size
db_signature = '''(name text, organisers text, mainstudentname text,
                mainstudentemail text, teacher text, summary text,
                date text, time text, venue text, whosetup text,
                setup text, classtimebool text, setuptime text,
                productsbool text, productsresponsibility text,
                furniturebool text, furniture text, assistancebool text,
                financial text, logistical text, materials text, risks text,
                requestdetails text, cashtinbool text, floatbool text,
                cashsupervise text, organisation text, paymentdetails text,
                eventhash text, approval text)''' # signature for event table in sqlite
cur.execute('CREATE TABLE IF NOT EXISTS events {}'.format(db_signature)) # create table if it doesn't exist
atexit.register(lambda: con.close()) # autoclose database

currentDate = datetime.datetime.now() # get date
currentYear = currentDate.year # get current year

def parse_calendar(filename): # function to parse calendar files
    wordDoc = Document(filename) # open document
    lastNum = 0 # last day number checked (0 for none checked)
    currentMonth = 1 # start at Jan
    datesTaken = [] # list to store dates taken
    conflicts = [] # list to store info for date conflict gui
    for table in wordDoc.tables: # loop through tables in document
        for row in table.rows: # loop through table rows
            for cell in row.cells: # loop through each cell
                cell_data = list(filter(lambda x: x, cell.text.split())) # get a list of words in the cell
                
                if len(cell_data) > 0 and cell_data[0].isdigit(): # data validation: check theres a day number
                    if len(cell_data) > 2: # data validation: check that the event contains text beyond two tokens
                        day = int(cell_data[0]) # extract day number as integer
                        
                        if day < lastNum: # data validation: check that subsequent date is larger than previous
                            currentMonth = currentMonth + 1 # increment month
                        
                        datesTaken.append(datetime.date(currentYear, currentMonth, day).isoformat()) # add date to list
                        conflicts.append(cell.text[len(cell_data[0])+1:]) # add cell text to conflict list
                        lastNum = day # change last day to processed day
    return dict(zip(datesTaken, conflicts)) # convert to dictionary and return
    
calendar = parse_calendar('calendar.docx') # parse school calendar
lunchtime_calendar = parse_calendar('lunchtimecalendar.docx') # parse lunch calendar

# decorator to check authorization for privileged operations
def privileged(func):
    @wraps(func) # wrap function copying all special methods and attributes such as __doc__ (necessary for flask compatibility)
    def wrapper(*args, **kwargs): # wrap arguments and keyword arguments in a function
        if auth.get(session.get('user')): # check if session exists
            return func(*args, **kwargs) # allow privileged access
        else: # not logged in
            return render_template('login.html') # redirect to login page
    return wrapper # return wrapped function
    
# context manager to handle sql transactions
# https://charlesleifer.com/blog/going-fast-with-sqlite-and-python/
@contextmanager # use this function in with statements for RAII style behaviour
def transaction(conn): # transaction handling function
    # We must issue a "BEGIN" explicitly when running in auto-commit mode.
    conn.execute('BEGIN')
    try:
        # Yield control back to the caller.
        yield
    except:
        conn.rollback()  # Roll back all changes if an exception occurs.
        raise
    else:
        conn.commit() # commit changes
        
# https://stackoverflow.com/questions/41129921/validate-an-iso-8601-datetime-string-in-python
def datetime_valid(dt_str): # function to check if date is valid
    try: # handle error
        date = datetime.fromisoformat(dt_str) # attempt string to date conversion
        year = date.year # get event year
        if not (year == currentYear and date.month >= currentDate.month and date.day >= currentDate.day): # cant add an event to the past
            return False # fail
    except:
        return False # if there's an error, it's not a valid date
    return True # date is valid

def handle_event(request): # data spec event handling logic function
    lst = ["name", "organisers", "mainstudentname",
           "mainstudentemail", "teacher", "summary",
           "date", "time", "venue", "whosetup",
           "setup", "classtimebool", "setuptime",
           "productsbool", "productsresponsibility",
           "furniturebool", "furniture", "assistancebool",
           "financial", "logistical", "materials", "risks",
           "requestdetails", "cashtinbool", "floatbool",
           "cashsupervise", "organisation", "paymentdetails"] # data attributes from html form
    data = [request.form.get(i,"").strip() for i in lst] # put data in a list
    return data # return the data
    
def validate_event(data): # event validation logic function
    pattern = re.compile('((1[0-2]|0?[1-9]):([0-5][0-9]) ?([AaPp][Mm]))') # time regex
    pattern2 = re.compile("^[a-zA-Z0-9.!#$%&'*+\/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$") # email regex
    if not (all(data[0:14]) and data[15] and data[17] and data[26] and data[25]): # existence check
        return False
    elif not all(map([data[11], data[13], data[15], data[17], data[26], data[25]], lambda x: (x == "Yes" or x == "No"))): # validate radio button
        return False
    elif not ((data[11] == "Yes") == bool(data[12]) and (data[13] == "Yes") == bool(data[14]) and (data[15] == "Yes") == bool(data[16])): # ensure optional fields filled
        return False
    elif not ((bool(data[18]) and bool(data[19]) and bool(data[20]) and bool(data[21])) == bool(data[22])): # handle optional request details
        return False
    elif not datetime_valid(data[6]): # validate date
        return False
    elif not (pattern.match(data[7]) and pattern.match(data[12])): # validate time
        return False
    elif not (pattern2.match(data[3]) and "." in data[3]): # validate email, don't accept weird but technically valid RFC formats
        return False
    else:
        return True # data passes all validation checks
        
@app.route("/") # default route
def default():
    return redirect(url_for('newevent')) # redirect to new event page

@app.route("/login") # login frontend route
def login():
    if auth.get(session.get('user')): # check user is logged in
        return redirect(url_for('manager')) # redirect to manager page
    else:
        return render_template('login.html', fail=request.args.get("fail")) # login failed, display failure message

@app.route("/loginpost", methods=['POST']) # backend data handling for login
def loginpost():
    if request.form.get("username") and auth.get(request.form.get("username")) == request.form.get("password"): # validate login (uses short circuiting logic)
        print("login success")
        session['user'] = request.form.get("username") # set session cookie in the browser to maintain login
        return redirect(url_for('manager')) # redirect to manager page
    else:
        print("login fail") # validation failed
        return redirect(url_for('login')+"?fail=true") # show failure message to user
        
@app.route("/logout") # logout route
@privileged # privileged operation
def logout():
    session['user'] = None # delete user session cookie
    return redirect(url_for('login')) # redirect to login page

@app.route("/manager") # manager route
@privileged # privileged operation
def manager():
    pending = [list(i) for i in cur.execute('SELECT * FROM events WHERE approval = "pending"').fetchall()] # select pending events from the database
    approved = cur.execute('SELECT * FROM events WHERE approval = "approved"').fetchall() # select approved events
    rejected = cur.execute('SELECT * FROM events WHERE approval = "rejected"').fetchall() # select rejected events
    for count, i in enumerate(pending): # loop the pending events
        print(i)
        date = i[6] # get the date
        conflict1 = calendar.get(date) # find conflicts in the school calendar
        conflict2 = lunchtime_calendar.get(date) # find conflicts in the lunchtime calendar
        pending[count].append(conflict1) # add conflict to pending event
        pending[count].append(conflict2) # add second conflict to pending event
            
    return render_template('manager.html', pending=pending, approved=approved, rejected=rejected) # render the manager gui with the calculated data

# new event route
@app.route("/newevent")
def newevent():
    return render_template('newevent.html', 
                           fail=request.args.get("fail"),
                           schoolcalendar=schoolcalendar,
                           activitycalendar=activitycalendar) # render new event passing url of school calendar, activity data, booolean for prior login failure for fail message
                           
@app.route("/neweventpost", methods=['POST']) # backend data handling for new event
def neweventpost():
    data = handle_event(request) # handle event data parsing
    if validate_event(data) == False: # validate data
        redirect(url_for('newevent')+"?fail=true") # redirect to fail page if validation fails
    d_hash = hashlib.sha224(str(data).encode("utf-8")).hexdigest() # calculate sha224 hash
    data.append(d_hash) # append hash to data in database
    data.append("pending") # set new event as pending approval
    print(str(data)) # print for debugging
    cur.execute('INSERT INTO events VALUES({})'.format(('?,' * 30)[0:-1]), data) # insert data into database, autoformat db-api to prevent sql injection
    return redirect(url_for('progress', eventhash=d_hash)) # redirect to progress page passing the hash
    
@app.route("/progress/<eventhash>") # progress page with event hash
def progress(eventhash): # accept event hash
    row = cur.execute('SELECT * FROM events WHERE eventhash = ?', (eventhash,)).fetchone() # fetch one row of data from the database
    approval = row[29] # and index approval status
    teacher = row[4] # get lead teacher
    print(eventhash)
    teachers = [names.get(i) for i in auth if names.get(i) != None] # get names of teachers
    print(teachers)
    return render_template('progress.html', lead=teacher, teachers=teachers, approval=approval) # pass teachers and approval status (currently approval is simultaneous for all teachers)
    
@app.route("/editevent/<eventhash>") # event edit page for Ms. Nguyen to edit events
@privileged # privileged user access only
def editevent(eventhash):
    event = cur.execute('SELECT * FROM events WHERE eventhash = ?', (eventhash,)).fetchone() # select event row from the database (event table)
    return render_template('editevent.html', fail=request.args.get("fail"), # render page passing necessary data
                           schoolcalendar=schoolcalendar,
                           activitycalendar=activitycalendar,
                           event=event, eventhash=eventhash) # passing event and event hash to fill the form fields
   
@app.route("/editeventpost", methods=['POST']) # handle routing for event editing backend
@privileged # privileged access
def editeventpost():
    data = handle_event(request) # process event data
    if validate_event(data) == False: # validate event data
        return redirect(url_for('editevent', eventhash=data[28])+"?fail=true") # validation failed, redirect user
    data.append(request.form.get(eventhash, "").strip()) # add formatted event hash to data
    data.append("pending") # set event as pending
    with transaction(con): # create a database transaction for ACID guarantees - ie. no database corruption even if there's power failure or OS crashes
        cur.execute('DELETE FROM events WHERE eventhash = ?', (data[28],)) # delete previous data in the database
        cur.execute('INSERT INTO events VALUES({})'.format(('?,' * 30)[0:-1]), data) # insert new data into the database
    return redirect(url_for('manager')) # redirect to manager page
        
@app.route("/approveevent/<eventhash>") # event approval handled with a GET request
@privileged # privileged operation
def approveevent(eventhash):
    cur.execute('UPDATE events SET approval = "approved" WHERE eventhash = ?', (eventhash,)) # update event event approval to approved
    return redirect(url_for('manager')) # redirect back to manager page
    
@app.route("/rejectevent/<eventhash>") # event rejection route
@privileged # privileged user 
def rejectevent(eventhash):
    cur.execute('UPDATE events SET approval = "rejected" WHERE eventhash = ?', (eventhash,)) # update event approval to rejected
    return redirect(url_for('manager')) # redirect back to manager page

# account creation outside of project scope       
#@app.route("/newaccount")
#@privileged
#def newaccount():
#    return render_template('newaccount.html')
    
#@app.route("/newaccountpost", methods=['POST'])
#@privileged
#def newaccountpost():
#    pass

# check file is being run                           
if __name__ == "__main__":
    app.run() # run app

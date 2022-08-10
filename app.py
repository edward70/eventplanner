from flask import *
import sqlite3, atexit, hashlib, datetime
from functools import wraps
from docx import Document
from filters import nl2br

app = Flask(__name__)
app.jinja_env.filters['nl2br'] = nl2br

# hardcoded constants
auth = {"username": "password"} # username -> password
names = {"username": "John Doe"} # username -> real name
approvalreqs = ["username"] # usernames required to approve events
schoolcalendar = "https://docs.google.com/document/d/1IhUHiIH9ctDlDJ2-_vLI42qQm-MGW5-Yxxv0xx_8bQo/edit?usp=sharing"
activitycalendar = "https://docs.google.com/document/d/e/2PACX-1vT12_PabQ-wKDFeGW26U1fAT9KhByozRazm7CJcLqHFqfB6cpGpRhHCmOWmIAZOSWpPbIvtqyNqvo8J/pub?embedded=true"
app.secret_key = "4Fa!R6w1@wkbMUSHO47r7#zmn"

# disable thread checking since sqlite3 is thread safe, enable autocommit for faster writes
con = sqlite3.connect('data.db', check_same_thread=False, isolation_level=None)
cur = con.cursor()
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
                eventhash text, approval text)'''
cur.execute('CREATE TABLE IF NOT EXISTS events {}'.format(db_signature))
atexit.register(lambda: con.close())

currentYear = datetime.datetime.now().year

def parse_calendar(filename):
    wordDoc = Document(filename)
    lastNum = 0
    currentMonth = 1
    datesTaken = []
    conflicts = []
    for table in wordDoc.tables:
        for row in table.rows:
            for cell in row.cells:
                cell_data = list(filter(lambda x: x, cell.text.split()))
                
                if len(cell_data) > 0 and cell_data[0].isdigit(): # check theres a day number
                    if len(cell_data) > 2:
                        day = int(cell_data[0]) # extract day number
                        
                        if day < lastNum:
                            currentMonth = currentMonth + 1 # increment month
                        
                        datesTaken.append(datetime.date(currentYear, currentMonth, day).isoformat())
                        conflicts.append(cell.text[len(cell_data[0])+1:])
                        lastNum = day
    return dict(zip(datesTaken, conflicts))
    
calendar = parse_calendar('calendar.docx')
lunchtime_calendar = parse_calendar('lunchtimecalendar.docx')

# decorator to check authorization for privileged operations
def privileged(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if auth.get(session.get('user')):
            return func(*args, **kwargs)
        else:
            return render_template('login.html')
    return wrapper

@app.route("/")
def hello_world():
    return "<p>Hello, World!</p>"

@app.route("/login")
def login():
    if auth.get(session.get('user')):
        return redirect(url_for('manager'))
    else:
        return render_template('login.html', fail=request.args.get("fail"))

@app.route("/loginpost", methods=['POST'])
def loginpost():
    if request.form.get("username") and auth.get(request.form.get("username")) == request.form.get("password"):
        print("login success")
        session['user'] = request.form.get("username")
        return redirect(url_for('manager'))
    else:
        print("login fail")
        return redirect(url_for('login')+"?fail=true")
        
@app.route("/logout")
@privileged
def logout():
    session['user'] = None
    return redirect(url_for('login'))

@app.route("/manager")
@privileged
def manager():
    pending = [list(i) for i in cur.execute('SELECT * FROM events WHERE approval = "pending"').fetchall()]
    approved = cur.execute('SELECT * FROM events WHERE approval = "approved"').fetchall()
    rejected = cur.execute('SELECT * FROM events WHERE approval = "rejected"').fetchall()
    for count, i in enumerate(pending):
        print(i)
        date = i[6]
        conflict1 = calendar.get(date)
        conflict2 = lunchtime_calendar.get(date)
        pending[count].append(conflict1)
        pending[count].append(conflict2)
            
    return render_template('manager.html', pending=pending, approved=approved, rejected=rejected)

@app.route("/newevent")
def newevent():
    return render_template('newevent.html', 
                           fail=request.args.get("fail"),
                           schoolcalendar=schoolcalendar,
                           activitycalendar=activitycalendar)
                           
@app.route("/neweventpost", methods=['POST'])
def neweventpost():
    lst = ["name", "organisers", "mainstudentname",
           "mainstudentemail", "teacher", "summary",
           "date", "time", "venue", "whosetup",
           "setup", "classtimebool", "setuptime",
           "productsbool", "productsresponsibility",
           "furniturebool", "furniture", "assistancebool",
           "financial", "logistical", "materials", "risks",
           "requestdetails", "cashtinbool", "floatbool",
           "cashsupervise", "organisation", "paymentdetails"]
    data = [request.form.get(i,"") for i in lst]
    d_hash = hashlib.sha224(str(data).encode("utf-8")).hexdigest()
    data.append(d_hash)
    data.append("pending")
    print(str(data))
    cur.execute('INSERT INTO events VALUES({})'.format(('?,' * 30)[0:-1]), data)
    return redirect(url_for('progress', eventhash=d_hash))
    
@app.route("/progress/<eventhash>")
def progress(eventhash):
    print(eventhash)
    teachers = [names.get(i) for i in auth if names.get(i) != None]
    print(teachers)
    return render_template('progress.html', teachers=teachers)
    
@app.route("/editevent/<eventhash>")
@privileged
def editevent(eventhash):
    event = cur.execute('SELECT * FROM events WHERE eventhash = ?', (eventhash,)).fetchone()
    return render_template('editevent.html', event=event)
        
@app.route("/approveevent/<eventhash>")
@privileged
def approveevent(eventhash):
    cur.execute('UPDATE events SET approval = "approved" WHERE eventhash = ?', (eventhash,))
    return redirect(url_for('manager'))
    
@app.route("/rejectevent/<eventhash>")
@privileged
def rejectevent(eventhash):
    cur.execute('UPDATE events SET approval = "rejected" WHERE eventhash = ?', (eventhash,))
    return redirect(url_for('manager'))
    
@app.route("/cashhandling")
def cashhandling():
    return render_template('cashhandling.html')
       
if __name__ == "__main__":
    app.run()
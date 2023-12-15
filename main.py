from flask_mysqldb import MySQL, MySQLdb
from flask_bcrypt import Bcrypt
from flask import g
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
from flask import Flask, render_template, session, request, redirect, url_for, flash, jsonify
import os
from functools import wraps
from geventwebsocket.handler import WebSocketHandler
from gevent.pywsgi import WSGIServer
from io import BytesIO
from flask import send_from_directory

app = Flask(__name__)
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'chatdb'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'
app.secret_key = "this is my key"
app.config['UPLOAD_FOLDER'] = 'uploads'


mysql = MySQL(app)
bcrypt = Bcrypt(app)
# socketio = SocketIO(app)
socketio = SocketIO(app, async_mode='gevent', transports=['websocket', 'polling'])
if not os.path.isdir(app.config['UPLOAD_FOLDER']):
    os.mkdir(app.config['UPLOAD_FOLDER'])


def generate_hash(password):
    return bcrypt.generate_password_hash(password).decode('utf-8')


def check_password(password, hashed_password):
    return bcrypt.check_password_hash(hashed_password, password)


def is_logged_in(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'username' in session:
            username = session['username']

            try:
                cur = mysql.connection.cursor()
                cur.execute("SELECT * FROM users WHERE username = %s", [username])
                user = cur.fetchone()

                if user:
                    g.user = user  # Store the user in Flask's global context for easy access
                    return f(*args, **kwargs)

            except MySQLdb.Error as e:
                flash(str(e), "error")

            finally:
                cur.close()

        flash('Unauthorized, Please login', "error")
        return redirect(url_for('index'))

    return wrap


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['username']
        password = request.form['password']
        repassword = request.form['repassword']

        if password != repassword:
            flash("Password Mismatch!!!", 'error')
            return render_template('signup.html')

        try:
            cur = mysql.connection.cursor()

            # Hash the password before storing it in the database (consider using a secure hashing library)
            hashed_password = generate_hash(password)

            # Insert user information into the database
            cur.execute("INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                        (username, email, hashed_password))

            mysql.connection.commit()
            cur.close()

            flash('Sign Up Successful', 'success')
            return redirect(url_for('index'))
        except MySQLdb.Error as e:
            flash(str(e), "error")
            return render_template('signup.html')

    return render_template('signup.html')


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        try:
            cur = mysql.connection.cursor()

            # Retrieve user information from the database
            cur.execute("SELECT * FROM users WHERE username = %s", [username])
            user = cur.fetchone()

            if user and check_password(password, user['password']):
                session['logged_in'] = True
                session['username'] = username

                flash('Login Successful', 'success')
                return redirect(url_for('home'))
            else:
                flash('Invalid username or password', 'error')

        except MySQLdb.Error as e:
            flash(str(e), "error")

        finally:
            cur.close()

    return render_template('login.html')


@app.route('/home', methods=["GET", 'POST'])
@is_logged_in
def home():
    if request.method == "GET":
        user_id = g.user['id']
        username = g.user['username']
        return render_template('index.html', user_id=user_id, username=username)


@app.route('/logout')
@is_logged_in
def logout():
    session.clear()
    flash('You are now logged out', 'success')
    return redirect(url_for('index'))


@socketio.on('user_message')
def handle_user_message(data):
    user_msg = data.get('text', '')
    file = data.get('file')
    user_id = request.sid
    sender_name = session['username']
    print(sender_name, user_msg)
    if user_msg:
        # Process and send the user's text message to the chatbot
        bot_response = user_msg
        socketio.emit('bot_response', {'user_id': user_id, 'sender_name': sender_name, 'text': bot_response})

    if file:
        # Process and send the user's file to the chatbot
        # Convert the bytes back to a file-like object
        file_obj = BytesIO(file)

        # Get the original filename from the client (assuming it's included)
        original_filename = data.get('fileName')

        # Save the file with the original filename
        filename = secure_filename(original_filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        with open(file_path, 'wb') as f:
            f.write(file_obj.read())

        file_link = url_for('uploaded_file', filename=filename)
        socketio.emit('bot_response',
                      {'user_id': user_id, 'sender_name': sender_name, 'file': file_link, 'fileName': filename})


@socketio.on('bot_response')
def handle_bot_response(data):
    print(f"Received bot response: {data}")
    socketio.emit('bot_response', data, broadcast=True)


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/game')
@is_logged_in
def game():
    user_id = g.user['id']
    username = g.user['username']
    return render_template('twoGame.html', user_id=user_id, username=username)


@app.route('/weather')
@is_logged_in
def weather():
    user_id = g.user['id']
    username = g.user['username']
    return render_template('weather.html', user_id=user_id, username=username)


@app.route('/news')
@is_logged_in
def news():
    user_id = g.user['id']
    username = g.user['username']
    return render_template('news.html', user_id=user_id, username=username)


if __name__ == '__main__':
    # app.run(debug=True, port=8000)
    http_server = WSGIServer(('127.0.0.1', 5000), app, handler_class=WebSocketHandler)
    http_server.serve_forever()

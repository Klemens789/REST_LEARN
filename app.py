from datetime import datetime

from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_httpauth import HTTPTokenAuth
from marshmallow import Schema, fields, ValidationError
from flasgger import Swagger

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///books.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
auth = HTTPTokenAuth(scheme='Bearer')
swagger = Swagger(app, template_file='swagger.yaml')

API_TOKEN = "123456"

@auth.verify_token
def verify_token(token):
    return token == API_TOKEN

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)  # Nowe pole opisu książki
    available = db.Column(db.Boolean, default=True)  # Dodane pole dostępności
class Borrow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id', ondelete='CASCADE'), nullable=False)
    user_name = db.Column(db.String(100), nullable=False)
    borrow_date = db.Column(db.DateTime, nullable=False)
    return_date = db.Column(db.DateTime, nullable=True)

    book = db.relationship('Book', backref=db.backref('borrows', cascade='all, delete-orphan'))
class BorrowSchema(Schema):
    book_id = fields.Integer(required=True, error_messages={"required": "ID książki jest wymagane."})
    user_name = fields.String(required=True, error_messages={"required": "Nazwa użytkownika jest wymagana."})

borrow_schema = BorrowSchema()

class BookSchema(Schema):
    title = fields.String(required=True, error_messages={"required": "Tytuł jest wymagany."})
    author = fields.String(required=True, error_messages={"required": "Autor jest wymagany."})

book_schema = BookSchema()

@app.route('/')
def home():
    return "API działa z bazą danych!"

@app.route('/books', methods=['GET'])
@auth.login_required
def get_books():
    books = Book.query.all()
    return jsonify([{"id": book.id, "title": book.title, "author": book.author} for book in books])

@app.route('/books', methods=['POST'])
@auth.login_required
def add_book():
    try:
        data = request.get_json()
        book_schema.load(data)
        new_book = Book(title=data['title'], author=data['author'])
        db.session.add(new_book)
        db.session.commit()
        return jsonify({"message": "Książka została dodana!"}), 201
    except ValidationError as err:
        return jsonify({"errors": err.messages}), 400

@app.route('/books/<int:book_id>', methods=['PUT'])
@auth.login_required
def update_book(book_id):
    book = Book.query.get_or_404(book_id)
    data = request.get_json()
    book.title = data.get('title', book.title)
    book.author = data.get('author', book.author)
    db.session.commit()
    return jsonify({"message": "Książka została zaktualizowana!"})

@app.route('/books/<int:book_id>', methods=['DELETE'])
@auth.login_required
def delete_book(book_id):
    book = Book.query.get_or_404(book_id)
    db.session.delete(book)
    db.session.commit()
    return jsonify({"message": "Książka została usunięta!"})

@app.route('/add-book', methods=['GET', 'POST'])
@app.route('/add-book', methods=['GET', 'POST'])
def add_book_form():
    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        description = request.form['description']
        if not title or not author or not description:
            return "Wszystkie pola są wymagane!", 400
        new_book = Book(title=title, author=author, description=description)
        db.session.add(new_book)
        db.session.commit()
        return redirect(url_for('show_books'))
    return render_template('add_book.html')

@app.route('/show-books')
def show_books():
    books = Book.query.all()
    return render_template('books.html', books=books)

@app.route('/edit-book/<int:book_id>', methods=['GET', 'POST'])
def edit_book(book_id):
    book = Book.query.get_or_404(book_id)
    if request.method == 'POST':
        book.title = request.form['title']
        book.author = request.form['author']
        db.session.commit()
        return redirect('/show-books')
    return render_template('edit_book.html', book=book)

@app.route('/delete-book/<int:book_id>', methods=['POST'])
def remove_book(book_id):
    book = Book.query.get_or_404(book_id)
    db.session.delete(book)
    db.session.commit()
    return redirect('/show-books')

@app.route('/borrow', methods=['POST'])
@auth.login_required
def borrow_book():
    try:
        data = request.get_json()
        borrow_schema.load(data)

        book = Book.query.get(data['book_id'])

        if not book or not book.available:
            return jsonify({"error": "Książka jest już wypożyczona lub nie istnieje"}), 400

        borrow = Borrow(book_id=book.id, user_name=data['user_name'], borrow_date=datetime.now())
        book.available = False
        db.session.add(borrow)
        db.session.commit()
        return jsonify({"message": "Książka została wypożyczona!"}), 200

    except ValidationError as err:
        return jsonify({"errors": err.messages}), 400

@app.route('/return/<int:borrow_id>', methods=['POST'])
@auth.login_required
def return_book(borrow_id):
    borrow = Borrow.query.get_or_404(borrow_id)

    if borrow.return_date:
        return jsonify({"error": "Książka została już zwrócona"}), 400

    borrow.book.available = True
    borrow.return_date = datetime.now()
    db.session.commit()
    return jsonify({"message": "Książka została zwrócona!"})

@app.route('/borrow', methods=['GET'])
@auth.login_required
def get_borrowings():
    borrowings = Borrow.query.all()
    return jsonify([
        {
            "id": b.id,
            "book_title": b.book.title,
            "user_name": b.user_name,
            "borrow_date": b.borrow_date.strftime('%Y-%m-%d %H:%M:%S'),
            "return_date": b.return_date.strftime('%Y-%m-%d %H:%M:%S') if b.return_date else "Wypożyczona"
        } for b in borrowings
    ])

@app.route('/borrow-book/<int:book_id>', methods=['GET', 'POST'])
def borrow_book_form(book_id):
    book = Book.query.get_or_404(book_id)
    if request.method == 'POST':
        user_name = request.form['user_name']
        if not user_name:
            return "Proszę podać nazwę użytkownika", 400

        if not book.available:
            return "Książka jest już wypożyczona!", 400

        new_borrow = Borrow(book_id=book.id, user_name=user_name, borrow_date=datetime.now())
        book.available = False
        db.session.add(new_borrow)
        db.session.commit()
        return redirect(url_for('show_books'))

    return render_template('borrow_book.html', book=book)


@app.route('/return-book/<int:borrow_id>', methods=['POST'])
def return_book_form(borrow_id):
    borrow = Borrow.query.get_or_404(borrow_id)

    if borrow.return_date:
        return "Książka została już zwrócona!", 400

    borrow.book.available = True
    borrow.return_date = datetime.now()
    db.session.commit()
    return redirect(url_for('show_books'))


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Nie znaleziono zasobu."}), 404

@app.errorhandler(400)
def bad_request(error):
    return jsonify({"error": "Błędne żądanie."}), 400

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)

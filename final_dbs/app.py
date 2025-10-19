from flask import Flask, render_template, request, redirect, url_for, session
import mysql.connector
import hashlib

app = Flask(__name__)

# Secret key for session management
app.secret_key = 'vijaymalya'

# MySQL configuration
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="1545",
    database="restaurant_db"
)

# Landing Page
@app.route('/')
def landing():
    if 'loggedin' in session:
        is_admin = session.get('role') == 'admin'
    else:
        is_admin = False

    return render_template('landing.html', is_admin=is_admin)


# Register Page
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()
        address = request.form['address']
        mobile = request.form['mobile']
        dietary_preferences = ','.join(request.form.getlist('dietary_preferences'))

        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO users (name, email, password, address, mobile, dietary_preference)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (name, email, password, address, mobile, dietary_preferences)
        )
        db.commit()
        cursor.close()
        return redirect(url_for('login'))
    return render_template('register.html')

# Login Page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()

        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s AND password = %s", (email, password))
        user = cursor.fetchone()
        cursor.close()

        if user:
            session['loggedin'] = True
            session['id'] = user['id']
            session['name'] = user['name']
            session['email'] = user['email']
            session['mobile'] = user['mobile']
            session['address'] = user['address']
            session['dietary_preference'] = user['dietary_preference'].split(',') if user['dietary_preference'] else []
            print("Session Data:", session) 
            return redirect(url_for('menu_page'))
        else:
            return 'Incorrect email or password!'
    return render_template('login.html')


# Menu Page
@app.route('/menu', methods=['GET', 'POST'])
def menu_page():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    print("Session Data in Menu Page:", session)  # Debugging to verify session contents

    # Handle missing dietary_preference in session
    dietary_preference = session.get('dietary_preference', [])  # Default to empty list if key is missing
    cursor = db.cursor(dictionary=True)

    if dietary_preference:
        # Prepare query for filtering menu items by dietary preferences
        format_strings = ','.join(['%s'] * len(dietary_preference))
        query = f"SELECT id, name, price, dietary_type, description, image FROM menu WHERE dietary_type IN ({format_strings})"
        cursor.execute(query, dietary_preference)
    else:
        # Fetch all menu items if no dietary preferences are set
        query = "SELECT id, name, price, dietary_type, description, image FROM menu"
        cursor.execute(query)
    
    menu = cursor.fetchall()
    cursor.close()

    if request.method == 'POST':
        item_id = request.form.get('item_id')
        quantity = int(request.form.get('quantity', 1))
        print("Item ID:", item_id)
        print("Quantity:", quantity)

        # Input validation for item_id and quantity
        if not item_id:
            return "Error: item_id is missing.", 400
        
        if quantity < 1 or quantity > 10:
            return "Error: Quantity must be between 1 and 10.", 400

        cursor = db.cursor(dictionary=True)
        # Check if the item already exists in the cart
        cursor.execute("SELECT * FROM cart WHERE user_id = %s AND item_id = %s", (session['id'], item_id))
        existing_item = cursor.fetchone()

        if existing_item:
            # Update the quantity if the item exists
            new_quantity = existing_item['quantity'] + quantity
            if new_quantity > 10:
                return "Error: Quantity cannot exceed 10.", 400
            cursor.execute("UPDATE cart SET quantity = %s WHERE id = %s", (new_quantity, existing_item['id']))
        else:
            # Insert a new item into the cart
            cursor.execute("INSERT INTO cart (user_id, item_id, quantity) VALUES (%s, %s, %s)", (session['id'], item_id, quantity))

        db.commit()
        cursor.close()
        return redirect(url_for('menu_page'))

    return render_template('menu.html', menu=menu)


# Cart Page
@app.route('/cart', methods=['GET', 'POST'])
def cart_page():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    user_id = session['id']

    if request.method == 'POST':
        cart_id = request.form.get('cart_id')
        item_id = request.form.get('item_id')
        remove = request.form.get('remove')
        quantity = request.form.get('quantity')

        cursor = db.cursor()

        if remove == "true":
            # Remove item from cart
            cursor.execute("DELETE FROM cart WHERE id = %s AND user_id = %s", (cart_id, user_id))
        else:
            # Update quantity of the item in cart
            cursor.execute(
                "UPDATE cart SET quantity = %s WHERE id = %s AND item_id = %s AND user_id = %s",
                (quantity, cart_id, item_id, user_id)
            )
        db.commit()
        cursor.close()
        return redirect(url_for('cart_page'))

    # Fetch all cart items for this user
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT cart.id AS cart_id, menu.id AS item_id, menu.name, menu.price, cart.quantity 
        FROM cart 
        JOIN menu ON cart.item_id = menu.id 
        WHERE cart.user_id = %s
    """, (user_id,))
    cart_items = cursor.fetchall()
    cursor.close()

    # Calculate total price
    total_price = sum(item['price'] * item['quantity'] for item in cart_items)

    return render_template('cart.html', cart=cart_items, total=total_price)

@app.route('/place_order', methods=['POST'])
def place_order():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    user_id = session['id']
    cursor = db.cursor(dictionary=True)

    # Create a unique order group ID for this order batch
    cursor.execute("SELECT MAX(order_group_id) FROM orders")
    max_group_id = cursor.fetchone()['MAX(order_group_id)'] or 0
    new_group_id = max_group_id + 1

    # Fetch cart items for the user
    cursor.execute("SELECT item_id, quantity FROM cart WHERE user_id = %s", (user_id,))
    cart_items = cursor.fetchall()

    # Insert cart items into the orders table
    for item in cart_items:
        cursor.execute(
            """
            INSERT INTO orders (user_id, menu_id, quantity, order_group_id, order_date)
            VALUES (%s, %s, %s, %s, NOW())
            """,
            (user_id, item['item_id'], item['quantity'], new_group_id)
        )

    # Clear the cart after placing the order
    cursor.execute("DELETE FROM cart WHERE user_id = %s", (user_id,))
    db.commit()
    cursor.close()

    # Store the group ID in the session to display the delivery message
    session['last_order_group'] = new_group_id
    return redirect(url_for('orders_page'))



# Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('landing'))

# Admin Login Route
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()

        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s AND password = %s AND role = 'admin'", (email, password))
        admin = cursor.fetchone()
        cursor.close()

        if admin:
            session['admin_loggedin'] = True
            session['admin_id'] = admin['id']
            session['admin_name'] = admin['name']
            return redirect(url_for('admin_panel'))
        else:
            return "Invalid admin credentials! Please try again."

    return render_template('admin_login.html')

# Admin Panel Route
@app.route('/admin_panel', methods=['GET', 'POST'])
def admin_panel():
    if 'admin_loggedin' not in session or not session['admin_loggedin']:
        return redirect(url_for('admin_login'))

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM menu")
    menu_items = cursor.fetchall()
    cursor.close()

    # Group menu items by dietary recommendation
    grouped_menu = {}
    for item in menu_items:
        dietary_type = item['dietary_type']
        if dietary_type not in grouped_menu:
            grouped_menu[dietary_type] = []
        grouped_menu[dietary_type].append(item)

    return render_template('admin_panel.html', grouped_menu=grouped_menu)

@app.route('/remove_menu_item', methods=['POST'])
def remove_menu_item():
    if 'admin_loggedin' not in session or not session['admin_loggedin']:
        return redirect(url_for('admin_login'))

    menu_id = request.form['menu_id']
    cursor = db.cursor()

    try:
        # Delete associated entries in the orders table first
        cursor.execute("DELETE FROM orders WHERE menu_id = %s", (menu_id,))
        
        # Delete the menu item
        cursor.execute("DELETE FROM menu WHERE id = %s", (menu_id,))

        db.commit()
        message = "Menu item and its associated orders have been successfully removed."
    except mysql.connector.Error as err:
        db.rollback()
        message = f"Error: {err}"
    finally:
        cursor.close()

    return redirect(url_for('admin_panel'))



# Admin Panel Route for Adding Menu Items
@app.route('/add_menu_item', methods=['POST'])
def add_menu_item():
    if 'admin_loggedin' not in session:  # Ensure only admins can add items
        return redirect(url_for('admin_login'))

    name = request.form['name']
    price = request.form['price']
    dietary_type = request.form['dietary_type']
    description = request.form['description']
    image = request.form.get('image', 'default.jpg')  # Default image if none provided

    cursor = db.cursor()
    cursor.execute(
        """
        INSERT INTO menu (name, price, dietary_type, description, image)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (name, price, dietary_type, description, image)
    )
    db.commit()
    cursor.close()
    return redirect(url_for('admin_panel'))

@app.route('/orders', methods=['GET'])
def orders_page():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    user_id = session['id']
    cursor = db.cursor(dictionary=True)

    # Fetch user orders
    cursor.execute("""
        SELECT orders.order_group_id, menu.name, menu.price, orders.quantity,
               (menu.price * orders.quantity) AS total_price, orders.order_date
        FROM orders
        JOIN menu ON orders.menu_id = menu.id
        WHERE orders.user_id = %s
        ORDER BY orders.order_group_id DESC, orders.order_date DESC
    """, (user_id,))
    orders = cursor.fetchall()
    cursor.close()

    # Debugging output
    print("Orders fetched for user:", user_id)
    print(orders)

    # Group orders by order_group_id
    grouped_orders = {}
    for order in orders:
        group_id = order['order_group_id']
        if group_id not in grouped_orders:
            grouped_orders[group_id] = []
        grouped_orders[group_id].append(order)

    # Debug grouped orders
    print("Grouped Orders:", grouped_orders)

    # Check if delivery message should be shown
    show_delivery_message = 'last_order_group' in session
    last_order_group = session.pop('last_order_group', None)

    return render_template(
        'orders.html',
        grouped_orders=grouped_orders,
        show_delivery_message=show_delivery_message,
        last_order_group=last_order_group
    )


@app.route('/clear_session', methods=['GET'])
def clear_session():
    """Clears the session for debugging or user logout purposes."""
    session.clear()  # Clears all session data
    return "Session cleared! Please log in again."






if __name__ == '__main__':
    app.run( debug=True)

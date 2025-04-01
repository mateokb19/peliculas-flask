from flask import Flask, render_template, request, redirect, url_for
import mysql.connector
from math import ceil

app = Flask(__name__)

# Configuración de la base de datos
db_config = {
    'host': 'sakila-db.cz2qkwft4xrw.us-east-1.rds.amazonaws.com',
    'user': 'admin',
    'password': 'V4lu525.',
    'database': 'sakila'
}

# Constantes para la paginación
PER_PAGE = 10  # Películas por página
TOTAL_PELICULAS = 200  # Total de películas a mostrar

@app.route('/')
@app.route('/page/<int:page>')
def index(page=1):
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    
    offset = (page - 1) * PER_PAGE
    
    # Consulta modificada para incluir más información
    cursor.execute("""
        SELECT 
            f.film_id, 
            f.title, 
            f.description, 
            f.release_year,
            f.length,
            f.replacement_cost,
            f.rental_rate, 
            f.rental_duration, 
            f.rating,
            GROUP_CONCAT(c.name SEPARATOR ', ') AS categories
        FROM film f
        LEFT JOIN film_category fc ON f.film_id = fc.film_id
        LEFT JOIN category c ON fc.category_id = c.category_id
        WHERE f.rental_duration > 0
        GROUP BY f.film_id
        ORDER BY f.title
        LIMIT %s OFFSET %s
    """, (PER_PAGE, offset))
    
    peliculas = cursor.fetchall()
    
    # Calcular total de páginas
    cursor.execute("SELECT COUNT(*) as total FROM film WHERE rental_duration > 0")
    total_films = cursor.fetchone()['total']
    total_pages = ceil(min(total_films, TOTAL_PELICULAS) / PER_PAGE)
    
    cursor.close()
    conn.close()
    
    return render_template('index.html', 
                        peliculas=peliculas,
                        current_page=page,
                        total_pages=total_pages,
                        per_page=PER_PAGE,
                        TOTAL_PELICULAS=min(total_films, TOTAL_PELICULAS))

@app.route('/rentar/<int:film_id>', methods=['GET', 'POST'])
def rentar(film_id):
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    
    # Obtener información de la película
    cursor.execute("""
        SELECT f.title, f.rental_rate, f.rental_duration,
               f.release_year, f.length, f.replacement_cost,
               GROUP_CONCAT(c.name SEPARATOR ', ') AS categories
        FROM film f
        LEFT JOIN film_category fc ON f.film_id = fc.film_id
        LEFT JOIN category c ON fc.category_id = c.category_id
        WHERE f.film_id = %s
        GROUP BY f.film_id
    """, (film_id,))
    pelicula = cursor.fetchone()
    
    if request.method == 'POST':
        nombre = request.form['nombre']
        apellido = request.form['apellido']  # Nuevo campo
        email = request.form['email']
        
        try:
            # 1. Verificar o crear cliente
            cursor.execute("SELECT customer_id FROM customer WHERE email = %s", (email,))
            cliente = cursor.fetchone()
            
            if not cliente:
                # Crear nuevo cliente con apellido
                cursor.execute("""
                    INSERT INTO customer (store_id, first_name, last_name, email, address_id, active, create_date)
                    VALUES (1, %s, %s, %s, 1, 1, NOW())
                """, (nombre, apellido, email))  # Incluye apellido
                cliente_id = cursor.lastrowid
            else:
                cliente_id = cliente['customer_id']
                # Actualizar apellido si el cliente ya existe
                cursor.execute("""
                    UPDATE customer SET last_name = %s WHERE customer_id = %s
                """, (apellido, cliente_id))
            
            # 2. Encontrar inventario disponible
            cursor.execute("""
                SELECT inventory_id FROM inventory 
                WHERE film_id = %s 
                AND NOT EXISTS (
                    SELECT 1 FROM rental 
                    WHERE rental.inventory_id = inventory.inventory_id 
                    AND rental.return_date IS NULL
                )
                LIMIT 1
            """, (film_id,))
            inventario = cursor.fetchone()
            
            if inventario:
                inventory_id = inventario['inventory_id']
                
                # 3. Crear la renta
                cursor.execute("""
                    INSERT INTO rental (rental_date, inventory_id, customer_id, return_date, staff_id)
                    VALUES (NOW(), %s, %s, DATE_ADD(NOW(), INTERVAL %s DAY), 1)
                """, (inventory_id, cliente_id, pelicula['rental_duration']))
                
                rental_id = cursor.lastrowid
                
                # 4. Registrar el pago
                cursor.execute("""
                    INSERT INTO payment (customer_id, staff_id, rental_id, amount, payment_date)
                    VALUES (%s, 1, %s, %s, NOW())
                """, (cliente_id, rental_id, pelicula['rental_rate']))
                
                conn.commit()
            mensaje = f"¡Renta confirmada para {nombre} {apellido}! Has rentado '{pelicula['title']}'."
            return render_template('rentar.html', 
                                pelicula=pelicula,
                                mensaje=mensaje,
                                film_id=film_id,
                                nombre=nombre,  # Nuevo
                                apellido=apellido)  # Nuevo
            
        except Exception as e:
            conn.rollback()
            mensaje = f"Error al procesar la renta: {str(e)}"
            return render_template('rentar.html',
                               pelicula=pelicula,
                               mensaje=mensaje,
                               film_id=film_id)
        finally:
            cursor.close()
            conn.close()
    
    # GET request
    cursor.close()
    conn.close()
    return render_template('rentar.html', pelicula=pelicula, film_id=film_id)


if __name__ == '__main__':
    app.run(debug=True)
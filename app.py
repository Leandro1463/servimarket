from flask import Flask, jsonify, request, session
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import hashlib
import secrets
import os

app = Flask(__name__)
CORS(app, supports_credentials=True, origins=['*'])

# Configuración
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(BASE_DIR, "ecommerce.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = secrets.token_hex(16)  # Para sesiones
db = SQLAlchemy(app)

# ========== FUNCIÓN PARA ENCRIPTAR ==========
def hash_password(password):
    """Encriptar contraseña con SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()

# ========== MODELOS ==========
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(200), nullable=False)  # Contraseña encriptada
    es_premium = db.Column(db.Boolean, default=False)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)

class Servicio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.String(500), nullable=False)
    precio = db.Column(db.Float, nullable=False)
    vendedor_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    fecha_publicacion = db.Column(db.DateTime, default=datetime.utcnow)
    vendedor = db.relationship('Usuario', backref='servicios')

# ========== ENDPOINTS DE USUARIO ==========

@app.route('/api/registro', methods=['POST'])
def registrar_usuario():
    """Registrar un nuevo usuario"""
    datos = request.json
    email = datos.get('email')
    nombre = datos.get('nombre')
    password = datos.get('password')
    
    # Validaciones
    if not email or not nombre or not password:
        return jsonify({'error': 'Todos los campos son requeridos'}), 400
    
    # Verificar si ya existe
    usuario_existente = Usuario.query.filter_by(email=email).first()
    if usuario_existente:
        return jsonify({'error': 'El email ya está registrado'}), 400
    
    # Crear usuario con contraseña encriptada
    nuevo_usuario = Usuario(
        email=email,
        nombre=nombre,
        password=hash_password(password),
        es_premium=False
    )
    db.session.add(nuevo_usuario)
    db.session.commit()
    
    # Iniciar sesión automáticamente
    session['usuario_id'] = nuevo_usuario.id
    session['usuario_nombre'] = nuevo_usuario.nombre
    
    return jsonify({
        'mensaje': 'Registro exitoso',
        'usuario_id': nuevo_usuario.id,
        'nombre': nuevo_usuario.nombre,
        'email': nuevo_usuario.email,
        'es_premium': nuevo_usuario.es_premium
    }), 201

@app.route('/api/login', methods=['POST'])
def login_usuario():
    """Iniciar sesión"""
    datos = request.json
    email = datos.get('email')
    password = datos.get('password')
    
    if not email or not password:
        return jsonify({'error': 'Email y contraseña requeridos'}), 400
    
    usuario = Usuario.query.filter_by(email=email).first()
    if not usuario:
        return jsonify({'error': 'Usuario no encontrado'}), 404
    
    # Verificar contraseña
    if usuario.password != hash_password(password):
        return jsonify({'error': 'Contraseña incorrecta'}), 401
    
    # Guardar sesión
    session['usuario_id'] = usuario.id
    session['usuario_nombre'] = usuario.nombre
    
    return jsonify({
        'mensaje': 'Login exitoso',
        'usuario_id': usuario.id,
        'nombre': usuario.nombre,
        'email': usuario.email,
        'es_premium': usuario.es_premium
    })

@app.route('/api/logout', methods=['POST'])
def logout_usuario():
    """Cerrar sesión"""
    session.clear()
    return jsonify({'mensaje': 'Sesión cerrada'})

@app.route('/api/usuario/actual', methods=['GET'])
def usuario_actual():
    """Obtener el usuario logueado"""
    if 'usuario_id' in session:
        usuario = Usuario.query.get(session['usuario_id'])
        if usuario:
            return jsonify({
                'usuario_id': usuario.id,
                'nombre': usuario.nombre,
                'email': usuario.email,
                'es_premium': usuario.es_premium
            })
    return jsonify({'error': 'No hay sesión activa'}), 401

# ========== ENDPOINTS DE SERVICIOS (ACTUALIZADOS) ==========

@app.route('/api/servicios', methods=['GET'])
def obtener_servicios():
    """Obtener todos los servicios"""
    servicios = Servicio.query.all()
    return jsonify([
        {
            'id': s.id,
            'titulo': s.titulo,
            'descripcion': s.descripcion,  # Corregido: descripcion
            'precio': s.precio,
            'vendedor_id': s.vendedor_id,
            'vendedor_nombre': s.vendedor.nombre if s.vendedor else 'Anónimo'
        }
        for s in servicios
    ])

@app.route('/api/servicios', methods=['POST'])
def crear_servicio():
    """Publicar un nuevo servicio (requiere login)"""
    if 'usuario_id' not in session:
        return jsonify({'error': 'Debes iniciar sesión para publicar'}), 401
    
    datos = request.json
    nuevo_servicio = Servicio(
        titulo=datos['titulo'],
        descripcion=datos['descripcion'],
        precio=datos['precio'],
        vendedor_id=session['usuario_id']
    )
    db.session.add(nuevo_servicio)
    db.session.commit()
    return jsonify({'mensaje': 'Servicio creado', 'id': nuevo_servicio.id}), 201

@app.route('/api/servicios/<int:id>', methods=['DELETE'])
def eliminar_servicio(id):
    """Eliminar un servicio (solo si eres el dueño)"""
    if 'usuario_id' not in session:
        return jsonify({'error': 'Debes iniciar sesión'}), 401
    
    servicio = Servicio.query.get(id)
    if not servicio:
        return jsonify({'error': 'Servicio no encontrado'}), 404
    
    # Verificar que el usuario es el dueño
    if servicio.vendedor_id != session['usuario_id']:
        return jsonify({'error': 'No puedes eliminar servicios de otros usuarios'}), 403
    
    db.session.delete(servicio)
    db.session.commit()
    return jsonify({'mensaje': 'Servicio eliminado'})

@app.route('/api/mis-servicios', methods=['GET'])
def mis_servicios():
    """Obtener solo los servicios del usuario logueado"""
    if 'usuario_id' not in session:
        return jsonify({'error': 'Debes iniciar sesión'}), 401
    
    servicios = Servicio.query.filter_by(vendedor_id=session['usuario_id']).all()
    return jsonify([
        {
            'id': s.id,
            'titulo': s.titulo,
            'descripcion': s.descripcion,
            'precio': s.precio
        }
        for s in servicios
    ])

@app.route('/api/membresia/estado', methods=['GET'])
def estado_membresia():
    """Verificar si el sistema está en modo gratuito"""
    return jsonify({
        'modo_gratuito': True,
        'mensaje': 'Actualmente todo es gratis mientras construimos la comunidad'
    })

# ========== INICIALIZAR BASE DE DATOS ==========
with app.app_context():
    db.create_all()
    
    # Crear usuario de ejemplo si no existe
    if Usuario.query.count() == 0:
        usuario_demo = Usuario(
            email="demo@ejemplo.com",
            nombre="Usuario Demo",
            password=hash_password("123456"),
            es_premium=False
        )
        db.session.add(usuario_demo)
        db.session.commit()
        
        # Servicios de ejemplo para el usuario demo
        servicio1 = Servicio(
            titulo="Diseño de Logo",
            descripcion="Logo profesional en 24h",
            precio=50,
            vendedor_id=1
        )
        servicio2 = Servicio(
            titulo="Página Web",
            descripcion="Web de 3 páginas responsive",
            precio=200,
            vendedor_id=1
        )
        db.session.add_all([servicio1, servicio2])
        db.session.commit()
        print("✅ Base de datos creada con usuario demo (demo@ejemplo.com / 123456)")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("🚀 Servidor corriendo")
    print("📝 Usuario demo: demo@ejemplo.com | Contraseña: 123456")
    app.run(debug=False, host='0.0.0.0', port=port)
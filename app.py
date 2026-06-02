from flask import Flask, jsonify, request, session
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import hashlib
import secrets
import os

app = Flask(__name__)
CORS(app, supports_credentials=True, origins=['*'])

# Configuración
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Detectar si estamos en producción (Render) o local
if os.environ.get('DATABASE_URL'):
    # Usar PostgreSQL en producción
    database_url = os.environ.get('DATABASE_URL')
    # Render usa 'postgres://' pero SQLAlchemy necesita 'postgresql://'
    if database_url and database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    print("✅ Usando base de datos PostgreSQL (producción)")
else:
    # Usar SQLite en local
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(BASE_DIR, "ecommerce.db")}'
    print("✅ Usando base de datos SQLite (local)")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = secrets.token_hex(16)
db = SQLAlchemy(app)

# ========== FUNCIÓN PARA ENCRIPTAR ==========
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ========== MODELOS ==========

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(200), nullable=False)
    telefono = db.Column(db.String(50), nullable=True)
    whatsapp = db.Column(db.String(50), nullable=True)
    es_premium = db.Column(db.Boolean, default=False)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)

class Publicacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False)  # 'producto', 'servicio', 'local'
    titulo = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.String(500), nullable=False)
    precio = db.Column(db.Float, nullable=True)  # opcional para locales
    condicion = db.Column(db.String(20), nullable=True)  # 'nuevo', 'usado' (solo productos)
    ubicacion = db.Column(db.String(100), nullable=True)  # ciudad/barrio
    telefono_contacto = db.Column(db.String(50), nullable=True)
    whatsapp_contacto = db.Column(db.String(50), nullable=True)
    imagen_url = db.Column(db.String(500), nullable=True)  # para después con Cloudinary
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    fecha_publicacion = db.Column(db.DateTime, default=datetime.utcnow)
    visitas = db.Column(db.Integer, default=0)  # contador de vistas
    
    # Relación
    usuario = db.relationship('Usuario', backref='publicaciones')

# ========== ENDPOINTS DE USUARIO ==========

@app.route('/api/registro', methods=['POST'])
def registrar_usuario():
    datos = request.json
    email = datos.get('email')
    nombre = datos.get('nombre')
    password = datos.get('password')
    
    if not email or not nombre or not password:
        return jsonify({'error': 'Todos los campos son requeridos'}), 400
    
    usuario_existente = Usuario.query.filter_by(email=email).first()
    if usuario_existente:
        return jsonify({'error': 'El email ya está registrado'}), 400
    
    nuevo_usuario = Usuario(
        email=email,
        nombre=nombre,
        password=hash_password(password),
        es_premium=False
    )
    db.session.add(nuevo_usuario)
    db.session.commit()
    
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
    datos = request.json
    email = datos.get('email')
    password = datos.get('password')
    
    if not email or not password:
        return jsonify({'error': 'Email y contraseña requeridos'}), 400
    
    usuario = Usuario.query.filter_by(email=email).first()
    if not usuario:
        return jsonify({'error': 'Usuario no encontrado'}), 404
    
    if usuario.password != hash_password(password):
        return jsonify({'error': 'Contraseña incorrecta'}), 401
    
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
    session.clear()
    return jsonify({'mensaje': 'Sesión cerrada'})

@app.route('/api/usuario/actual', methods=['GET'])
def usuario_actual():
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

# ========== ENDPOINTS DE PUBLICACIONES ==========

@app.route('/api/publicaciones', methods=['GET'])
def obtener_publicaciones():
    """Obtener publicaciones con filtros"""
    tipo = request.args.get('tipo', None)
    q = request.args.get('q', '')
    min_precio = request.args.get('min_precio', 0, type=float)
    max_precio = request.args.get('max_precio', 1000000, type=float)
    ubicacion = request.args.get('ubicacion', '')
    
    query = Publicacion.query
    
    if tipo and tipo != '':
        query = query.filter(Publicacion.tipo == tipo)
    
    if q:
        query = query.filter(
            Publicacion.titulo.contains(q) | Publicacion.descripcion.contains(q)
        )
    
    if min_precio > 0 or max_precio < 1000000:
        query = query.filter(Publicacion.precio.between(min_precio, max_precio))
    
    if ubicacion:
        query = query.filter(Publicacion.ubicacion.contains(ubicacion))
    
    publicaciones = query.order_by(Publicacion.fecha_publicacion.desc()).all()
    
    return jsonify([
        {
            'id': p.id,
            'tipo': p.tipo,
            'titulo': p.titulo,
            'descripcion': p.descripcion,
            'precio': p.precio,
            'condicion': p.condicion,
            'ubicacion': p.ubicacion,
            'telefono_contacto': p.telefono_contacto,
            'whatsapp_contacto': p.whatsapp_contacto,
            'usuario_id': p.usuario_id,
            'vendedor_nombre': p.usuario.nombre if p.usuario else 'Anónimo',
            'fecha': p.fecha_publicacion.strftime('%d/%m/%Y'),
            'visitas': p.visitas
        }
        for p in publicaciones
    ])

@app.route('/api/publicaciones', methods=['POST'])
def crear_publicacion():
    """Crear una nueva publicacion"""
    if 'usuario_id' not in session:
        return jsonify({'error': 'Debes iniciar sesión'}), 401
    
    datos = request.json
    
    nueva = Publicacion(
        tipo=datos.get('tipo'),
        titulo=datos.get('titulo'),
        descripcion=datos.get('descripcion'),
        precio=datos.get('precio'),
        condicion=datos.get('condicion'),
        ubicacion=datos.get('ubicacion'),
        telefono_contacto=datos.get('telefono_contacto'),
        whatsapp_contacto=datos.get('whatsapp_contacto'),
        usuario_id=session['usuario_id']
    )
    
    db.session.add(nueva)
    db.session.commit()
    return jsonify({'mensaje': 'Publicación creada', 'id': nueva.id}), 201

@app.route('/api/publicaciones/<int:id>', methods=['PUT'])
def actualizar_publicacion(id):
    """Actualizar publicacion (solo dueño)"""
    if 'usuario_id' not in session:
        return jsonify({'error': 'Debes iniciar sesión'}), 401
    
    pub = Publicacion.query.get(id)
    if not pub:
        return jsonify({'error': 'No encontrada'}), 404
    
    if pub.usuario_id != session['usuario_id']:
        return jsonify({'error': 'No autorizado'}), 403
    
    datos = request.json
    if 'titulo' in datos:
        pub.titulo = datos['titulo']
    if 'descripcion' in datos:
        pub.descripcion = datos['descripcion']
    if 'precio' in datos:
        pub.precio = datos['precio']
    if 'ubicacion' in datos:
        pub.ubicacion = datos['ubicacion']
    if 'telefono_contacto' in datos:
        pub.telefono_contacto = datos['telefono_contacto']
    
    db.session.commit()
    return jsonify({'mensaje': 'Actualizada correctamente'})

@app.route('/api/publicaciones/<int:id>', methods=['DELETE'])
def eliminar_publicacion(id):
    """Eliminar publicacion (solo dueño)"""
    if 'usuario_id' not in session:
        return jsonify({'error': 'Debes iniciar sesión'}), 401
    
    pub = Publicacion.query.get(id)
    if not pub:
        return jsonify({'error': 'No encontrada'}), 404
    
    if pub.usuario_id != session['usuario_id']:
        return jsonify({'error': 'No autorizado'}), 403
    
    db.session.delete(pub)
    db.session.commit()
    return jsonify({'mensaje': 'Publicación eliminada'})

@app.route('/api/mis-publicaciones', methods=['GET'])
def mis_publicaciones():
    """Obtener publicaciones del usuario logueado"""
    if 'usuario_id' not in session:
        return jsonify({'error': 'Debes iniciar sesión'}), 401
    
    pubs = Publicacion.query.filter_by(usuario_id=session['usuario_id']).all()
    return jsonify([
        {
            'id': p.id,
            'tipo': p.tipo,
            'titulo': p.titulo,
            'precio': p.precio,
            'fecha': p.fecha_publicacion.strftime('%d/%m/%Y')
        }
        for p in pubs
    ])

@app.route('/api/membresia/estado', methods=['GET'])
def estado_membresia():
    return jsonify({
        'modo_gratuito': True,
        'mensaje': 'Actualmente todo es gratis mientras construimos la comunidad'
    })

# ========== ENDPOINTS DE ANALYTICS ==========

@app.route('/api/analytics/resumen', methods=['GET'])
def analytics_resumen():
    from datetime import timedelta
    
    total_usuarios = Usuario.query.count()
    total_publicaciones = Publicacion.query.count()
    productos = Publicacion.query.filter_by(tipo='producto').count()
    servicios = Publicacion.query.filter_by(tipo='servicio').count()
    locales = Publicacion.query.filter_by(tipo='local').count()
    usuarios_premium = Usuario.query.filter_by(es_premium=True).count()
    
    # Publicaciones por día (últimos 7 días)
    publicaciones_por_dia = []
    for i in range(6, -1, -1):
        fecha = datetime.now() - timedelta(days=i)
        fecha_inicio = datetime(fecha.year, fecha.month, fecha.day, 0, 0, 0)
        fecha_fin = fecha_inicio + timedelta(days=1)
        count = Publicacion.query.filter(
            Publicacion.fecha_publicacion >= fecha_inicio,
            Publicacion.fecha_publicacion < fecha_fin
        ).count()
        publicaciones_por_dia.append({
            'fecha': fecha.strftime('%d/%m'),
            'count': count
        })
    
    # Usuarios por día (últimos 7 días)
    usuarios_por_dia = []
    for i in range(6, -1, -1):
        fecha = datetime.now() - timedelta(days=i)
        fecha_inicio = datetime(fecha.year, fecha.month, fecha.day, 0, 0, 0)
        fecha_fin = fecha_inicio + timedelta(days=1)
        count = Usuario.query.filter(
            Usuario.fecha_registro >= fecha_inicio,
            Usuario.fecha_registro < fecha_fin
        ).count()
        usuarios_por_dia.append({
            'fecha': fecha.strftime('%d/%m'),
            'count': count
        })
    
    # Top 5 vendedores (más publicaciones)
    top_vendedores = db.session.query(
        Usuario.nombre,
        db.func.count(Publicacion.id).label('total')
    ).join(Publicacion, Usuario.id == Publicacion.usuario_id)\
     .group_by(Usuario.id)\
     .order_by(db.func.count(Publicacion.id).desc())\
     .limit(5)\
     .all()
    
    top_vendedores_list = [{'nombre': v[0], 'total': v[1]} for v in top_vendedores]
    
    # Precio promedio de publicaciones
    precio_promedio = db.session.query(db.func.avg(Publicacion.precio)).scalar() or 0
    
    return jsonify({
        'total_usuarios': total_usuarios,
        'total_publicaciones': total_publicaciones,
        'productos': productos,
        'servicios': servicios,
        'locales': locales,
        'usuarios_premium': usuarios_premium,
        'porcentaje_premium': round((usuarios_premium / total_usuarios * 100) if total_usuarios > 0 else 0, 1),
        'precio_promedio': round(precio_promedio, 2),
        'publicaciones_por_dia': publicaciones_por_dia,
        'usuarios_por_dia': usuarios_por_dia,
        'top_vendedores': top_vendedores_list
    })

@app.route('/api/analytics/usuarios', methods=['GET'])
def analytics_usuarios():
    usuarios = Usuario.query.all()
    resultado = []
    for u in usuarios:
        publicaciones_count = Publicacion.query.filter_by(usuario_id=u.id).count()
        resultado.append({
            'id': u.id,
            'nombre': u.nombre,
            'email': u.email,
            'es_premium': u.es_premium,
            'fecha_registro': u.fecha_registro.strftime('%Y-%m-%d %H:%M'),
            'total_publicaciones': publicaciones_count
        })
    return jsonify(resultado)

@app.route('/api/analytics/publicaciones', methods=['GET'])
def analytics_publicaciones():
    publicaciones = Publicacion.query.all()
    resultado = []
    for p in publicaciones:
        resultado.append({
            'id': p.id,
            'tipo': p.tipo,
            'titulo': p.titulo,
            'precio': p.precio,
            'vendedor': p.usuario.nombre if p.usuario else 'Anónimo',
            'fecha': p.fecha_publicacion.strftime('%Y-%m-%d %H:%M')
        })
    return jsonify(resultado)

# ========== RUTAS HTML (AL FINAL - IMPORTANTE) ==========

@app.route('/')
def inicio():
    try:
        with open('index.html', 'r', encoding='utf-8') as f:
            return f.read()
    except:
        return "🚀 ServiMarket API funcionando!"

@app.route('/index.html')
def index_html():
    return inicio()

@app.route('/dashboard')
def dashboard():
    try:
        with open('dashboard.html', 'r', encoding='utf-8') as f:
            return f.read()
    except:
        return "Dashboard no encontrado"

@app.route('/dashboard.html')
def dashboard_html():
    return dashboard()

@app.route('/<path:filename>')
def servir_html(filename):
    # No interferir con las rutas de API
    if filename.startswith('api/'):
        return "Ruta no disponible", 404
    if filename.endswith('.html'):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return "Archivo no encontrado", 404
    return "Ruta no disponible", 404

# ========== INICIALIZAR BASE DE DATOS ==========
with app.app_context():
    db.create_all()
    
    if Usuario.query.count() == 0:
        usuario_demo = Usuario(
            email="demo@ejemplo.com",
            nombre="Usuario Demo",
            password=hash_password("123456"),
            es_premium=False
        )
        db.session.add(usuario_demo)
        db.session.commit()
        print("✅ Base de datos creada con usuario demo")
        
        # Publicaciones de ejemplo
        pub1 = Publicacion(
            tipo="producto",
            titulo="iPhone 12 usado",
            descripcion="Excelente estado, 128GB, color negro, con cargador original",
            precio=350,
            condicion="usado",
            ubicacion="CABA - Belgrano",
            telefono_contacto="11-1234-5678",
            usuario_id=1
        )
        pub2 = Publicacion(
            tipo="servicio",
            titulo="Plomero matriculado",
            descripcion="Reparaciones de pérdidas, instalación de cañerías, urgencias 24hs",
            precio=15000,
            ubicacion="Zona Norte",
            telefono_contacto="11-8765-4321",
            usuario_id=1
        )
        pub3 = Publicacion(
            tipo="local",
            titulo="Panadería La Esquina",
            descripcion="Pan fresco todos los días, facturas, sandwiches, atención al público",
            ubicacion="Av. Siempre Viva 123, San Isidro",
            telefono_contacto="11-5566-7788",
            usuario_id=1
        )
        db.session.add_all([pub1, pub2, pub3])
        db.session.commit()
        print("✅ Publicaciones de ejemplo creadas")

# ========== EJECUTAR SERVIDOR ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("🚀 Servidor corriendo")
    print("📝 Usuario demo: demo@ejemplo.com | Contraseña: 123456")
    app.run(debug=False, host='0.0.0.0', port=port)
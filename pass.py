from werkzeug.security import generate_password_hash
generate_password_hash("admin123")
print("la contraseña hash es: ", generate_password_hash("admin123"))
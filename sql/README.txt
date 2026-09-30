DB재적재

chcp 65001

set PGCLIENTENCODING=UTF8

"C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -d portfolio_db -f "C:\Users\SAMSUNG\Desktop\project_1\sql\04_create_load_clickstream.sql"

"C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -d portfolio_db -f "C:\Users\SAMSUNG\Desktop\project_1\sql\08_export_tableau_star.sql"
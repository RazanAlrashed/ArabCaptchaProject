from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.db.models import Base
from datetime import datetime

# ==========================================
# SQLite database (SOURCE)
# ==========================================
SQLITE_URL = "sqlite:///./arabcaptcha.db"

# ==========================================
# Neon PostgreSQL database (TARGET)
# ==========================================
NEON_URL = "postgresql://neondb_owner:npg_poKDH7SnlG4b@ep-green-rice-ap6gc3xx-pooler.c-7.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
# إنشاء الاتصالات

# =========================================================
# Create engines
# =========================================================
sqlite_engine = create_engine(SQLITE_URL)
neon_engine = create_engine(NEON_URL)

# =========================================================
# Create tables in Neon
# =========================================================
print("Creating tables in Neon...")
Base.metadata.create_all(bind=neon_engine)

# =========================================================
# Sessions
# =========================================================
SQLiteSession = sessionmaker(bind=sqlite_engine)
NeonSession = sessionmaker(bind=neon_engine)

sqlite_session = SQLiteSession()
neon_session = NeonSession()

# =========================================================
# Boolean columns
# =========================================================
BOOLEAN_COLUMNS = {
    "needs_challenge",
    "active",
    "passed",
    "is_human_verified",
    "is_verified",
}

# =========================================================
# Datetime columns
# =========================================================
DATETIME_COLUMNS = {
    "created_at",
    "updated_at",
    "verified_at",
    "timestamp",
    "added_at",
    "session_created_at",
    "expires_at",
}

try:

    # =====================================================
    # IMPORTANT:
    # Order matters بسبب العلاقات Foreign Keys
    # =====================================================
    table_order = [
        "client_site",
        "client_domain",
        "site_session",
        "behavior_log",
        "word",
        "reference_word",
        "low_confidence_word",
        "challenge",
        "attempt",
        "low_confidence_submission",
        "low_confidence_consensus",
    ]

    for table_name in table_order:

        print(f"\nMigrating table: {table_name}")

        # =================================================
        # Read rows from SQLite
        # =================================================
        result = sqlite_session.execute(
            text(f"SELECT * FROM {table_name}")
        )

        rows = result.mappings().all()

        if not rows:
            print("No data found.")
            continue

        inserted = 0

        for row in rows:

            cleaned_row = {}

            for key, value in row.items():

                # =========================================
                # NULL handling
                # =========================================
                if value in ["", "None"]:
                    cleaned_row[key] = None
                    continue

                # =========================================
                # DATETIME handling
                # =========================================
                if key in DATETIME_COLUMNS:

                    # Invalid SQLite datetime values
                    if value in [0, 1, "0", "1", "", "None", None]:

                        # حط تاريخ افتراضي بدل NULL
                        cleaned_row[key] = datetime.utcnow()

                    elif isinstance(value, datetime):
                        cleaned_row[key] = value

                    else:
                        cleaned_row[key] = value

                    continue

                # =========================================
                # BOOLEAN handling
                # =========================================
                if key in BOOLEAN_COLUMNS:

                    if value in [1, "1", True, "true", "True"]:
                        cleaned_row[key] = True

                    elif value in [0, "0", False, "false", "False"]:
                        cleaned_row[key] = False

                    else:
                        cleaned_row[key] = None

                    continue

                # =========================================
                # Default
                # =========================================
                cleaned_row[key] = value

            # =================================================
            # Build INSERT query
            # =================================================
            columns = ", ".join(cleaned_row.keys())

            placeholders = ", ".join(
                [f":{key}" for key in cleaned_row.keys()]
            )

            insert_query = text(
                f"""
                INSERT INTO {table_name} ({columns})
                VALUES ({placeholders})
                """
            )

            # =================================================
            # Execute insert
            # =================================================
            neon_session.execute(insert_query, cleaned_row)

            inserted += 1

        # =====================================================
        # Commit after each table
        # =====================================================
        neon_session.commit()

        print(f"Inserted {inserted} rows.")

    print("\n✅ Migration completed successfully!")

except Exception as e:

    neon_session.rollback()

    print("\n❌ Migration failed:")
    print(e)

finally:

    sqlite_session.close()
    neon_session.close()
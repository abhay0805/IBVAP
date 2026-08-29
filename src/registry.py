import sqlite3

DB_PATH = "output/ibvap.db"


def add_vehicle(plate_number, vehicle_type, owner, status="VERIFIED"):

    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO vehicles
        (plate_number, vehicle_type, owner, status)
        VALUES (?, ?, ?, ?)
    """, (
        plate_number,
        vehicle_type,
        owner,
        status
    ))

    connection.commit()
    connection.close()

    print(f"Vehicle added: {plate_number}")


def list_vehicles():

    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT plate_number, vehicle_type, owner, status
        FROM vehicles
    """)

    vehicles = cursor.fetchall()

    connection.close()

    print("\n===== VEHICLE REGISTRY =====")

    if not vehicles:
        print("No vehicles registered.")
        return

    for vehicle in vehicles:
        print(
            f"Plate: {vehicle[0]} | "
            f"Type: {vehicle[1]} | "
            f"Owner: {vehicle[2]} | "
            f"Status: {vehicle[3]}"
        )


if __name__ == "__main__":

    add_vehicle(
        "AI 7060 EC",
        "SUV",
        "SSB Patrol"
    )

    add_vehicle(
        "AA 3325 MM",
        "TRUCK",
        "Border Supply"
    )

    list_vehicles()
import { NextRequest, NextResponse } from "next/server";
import { getPlateRecords } from "@/lib/dataStore";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const query = searchParams.get("query")?.toLowerCase();

    let plates = await getPlateRecords();

    if (query) {
      plates = plates.filter(
        (p) =>
          p.plate_text.toLowerCase().includes(query) ||
          p.camera_id.toLowerCase().includes(query) ||
          p.object_type.toLowerCase().includes(query)
      );
    }

    return NextResponse.json({
      total: plates.length,
      plates,
    });
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to query ANPR plates", details: String(error) },
      { status: 500 }
    );
  }
}

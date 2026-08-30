import { NextRequest, NextResponse } from "next/server";
import { getEvents } from "@/lib/dataStore";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const camera = searchParams.get("camera");
    const eventType = searchParams.get("type");
    const search = searchParams.get("search")?.toLowerCase();
    const limit = parseInt(searchParams.get("limit") || "100", 10);

    let events = await getEvents();

    if (camera && camera !== "ALL") {
      events = events.filter((e) => e.camera_id === camera);
    }
    if (eventType && eventType !== "ALL") {
      events = events.filter((e) => e.event_type === eventType);
    }
    if (search) {
      events = events.filter(
        (e) =>
          e.event_id.toLowerCase().includes(search) ||
          e.object_type?.toLowerCase().includes(search) ||
          e.plate_text?.toLowerCase().includes(search) ||
          e.camera_id?.toLowerCase().includes(search)
      );
    }

    return NextResponse.json({
      total: events.length,
      events: events.slice(0, limit),
    });
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to query events", details: String(error) },
      { status: 500 }
    );
  }
}

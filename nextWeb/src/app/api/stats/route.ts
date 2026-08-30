import { NextResponse } from "next/server";
import { getSystemStats } from "@/lib/dataStore";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const stats = await getSystemStats();
    return NextResponse.json(stats);
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to load system stats", details: String(error) },
      { status: 500 }
    );
  }
}

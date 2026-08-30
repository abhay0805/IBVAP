import { NextRequest, NextResponse } from "next/server";
import { acknowledgeAlert } from "@/lib/dataStore";

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const alertId = params.id;
    await acknowledgeAlert(alertId);
    return NextResponse.json({ success: true, alertId, status: "ACKNOWLEDGED" });
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to acknowledge alert", details: String(error) },
      { status: 500 }
    );
  }
}

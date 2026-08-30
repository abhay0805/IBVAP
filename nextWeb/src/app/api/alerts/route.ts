import { NextRequest, NextResponse } from "next/server";
import { getAlerts } from "@/lib/dataStore";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const severity = searchParams.get("severity");
    const status = searchParams.get("status");
    const limit = parseInt(searchParams.get("limit") || "100", 10);

    let alerts = await getAlerts();

    if (severity && severity !== "ALL") {
      alerts = alerts.filter((a) => a.severity === severity);
    }
    if (status && status !== "ALL") {
      alerts = alerts.filter((a) => a.status === status);
    }

    return NextResponse.json({
      total: alerts.length,
      alerts: alerts.slice(0, limit),
    });
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to query alerts", details: String(error) },
      { status: 500 }
    );
  }
}

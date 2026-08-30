import { NextResponse } from "next/server";
import { detectionState } from "@/lib/detectState";

export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json(detectionState);
}

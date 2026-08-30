import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import { PATHS } from "@/lib/config";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  try {
    const rawPath = params.path.join("/");
    let targetPath = path.resolve(PATHS.root, rawPath);

    if (!fs.existsSync(targetPath)) {
      targetPath = path.resolve(PATHS.outputDir, rawPath);
    }
    if (!fs.existsSync(targetPath)) {
      targetPath = path.resolve(PATHS.videosDir, rawPath);
    }

    if (!fs.existsSync(targetPath) || !fs.statSync(targetPath).isFile()) {
      return NextResponse.json({ error: "File not found", path: rawPath }, { status: 404 });
    }

    const stat = fs.statSync(targetPath);
    const fileSize = stat.size;
    const ext = path.extname(targetPath).toLowerCase();

    let contentType = "application/octet-stream";
    if (ext === ".jpg" || ext === ".jpeg") contentType = "image/jpeg";
    else if (ext === ".png") contentType = "image/png";
    else if (ext === ".mp4") contentType = "video/mp4";
    else if (ext === ".json") contentType = "application/json";

    const range = request.headers.get("range");

    if (range && contentType.startsWith("video/")) {
      const parts = range.replace(/bytes=/, "").split("-");
      const start = parseInt(parts[0], 10);
      const end = parts[1] ? parseInt(parts[1], 10) : fileSize - 1;
      const chunksize = end - start + 1;

      const fileStream = fs.createReadStream(targetPath, { start, end });
      let isClosed = false;

      const stream = new ReadableStream({
        start(controller) {
          fileStream.on("data", (chunk) => {
            if (!isClosed) {
              try {
                controller.enqueue(chunk);
              } catch {
                isClosed = true;
                fileStream.destroy();
              }
            }
          });
          fileStream.on("end", () => {
            if (!isClosed) {
              isClosed = true;
              try {
                controller.close();
              } catch {}
            }
          });
          fileStream.on("error", (err) => {
            if (!isClosed) {
              isClosed = true;
              try {
                controller.error(err);
              } catch {}
            }
          });
        },
        cancel() {
          isClosed = true;
          fileStream.destroy();
        },
      });

      return new NextResponse(stream, {
        status: 206,
        headers: {
          "Content-Range": `bytes ${start}-${end}/${fileSize}`,
          "Accept-Ranges": "bytes",
          "Content-Length": chunksize.toString(),
          "Content-Type": contentType,
        },
      });
    }

    const fileBuffer = fs.readFileSync(targetPath);
    return new NextResponse(fileBuffer, {
      headers: {
        "Content-Type": contentType,
        "Content-Length": fileSize.toString(),
        "Cache-Control": "public, max-age=3600",
      },
    });
  } catch (err) {
    return NextResponse.json(
      { error: "Error streaming media", details: String(err) },
      { status: 500 }
    );
  }
}

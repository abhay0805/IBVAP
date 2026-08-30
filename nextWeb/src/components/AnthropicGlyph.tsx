import React from "react";

export function AnthropicGlyph({ className = "w-4 h-4 text-ink" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      className={className}
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* 4-Spoke Radial Spike Mark */}
      <path d="M12 2C11.4 2 11 2.4 11 3V9.2L6.6 4.8C6.2 4.4 5.6 4.4 5.2 4.8C4.8 5.2 4.8 5.8 5.2 6.2L9.6 10.6H3.4C2.8 10.6 2.4 11 2.4 11.6C2.4 12.2 2.8 12.6 3.4 12.6H9.6L5.2 17C4.8 17.4 4.8 18 5.2 18.4C5.6 18.8 6.2 18.8 6.6 18.4L11 14V20.2C11 20.8 11.4 21.2 12 21.2C12.6 21.2 13 20.8 13 20.2V14L17.4 18.4C17.8 18.8 18.4 18.8 18.8 18.4C19.2 18 19.2 17.4 18.8 17L14.4 12.6H20.6C21.2 12.6 21.6 12.2 21.6 11.6C21.6 11 21.2 10.6 20.6 10.6H14.4L18.8 6.2C19.2 5.8 19.2 5.2 18.8 4.8C18.4 4.4 17.8 4.4 17.4 4.8L13 9.2V3C13 2.4 12.6 2 12 2Z" />
    </svg>
  );
}

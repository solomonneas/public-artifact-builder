import React from "react";

export function bootstrapDashboard() {
  return {
    title: "Sample Ops Dashboard",
    sections: ["build health", "service status", "incident review"],
  };
}


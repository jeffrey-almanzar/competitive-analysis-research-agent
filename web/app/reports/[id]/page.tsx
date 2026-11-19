import { notFound } from "next/navigation";
import ProgressView from "@/components/ProgressView";
import ReportView from "@/components/ReportView";
import { getRun } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const run = await getRun(id);
  if (!run) notFound();
  if (run.status === "succeeded" && run.report) {
    return <ReportView runId={run.id} report={run.report} />;
  }
  return <ProgressView initial={run} />;
}

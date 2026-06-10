import type { ColumnsType } from "antd/es/table";
import type { ContainerRow } from "../types";
import { PageHeader } from "../components/PageHeader";
import { RuntimeContainersPanel } from "./runtime/RuntimeContainersPanel";

type Props = {
  containerColumns: ColumnsType<ContainerRow>;
  containers: ContainerRow[];
};

export function RuntimeContainersPage({ containerColumns, containers }: Props) {
  return (
    <>
      <PageHeader title="Runtime Containers" />
      <RuntimeContainersPanel containerColumns={containerColumns} containers={containers} />
    </>
  );
}

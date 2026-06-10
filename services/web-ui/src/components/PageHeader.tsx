import { Flex, Typography } from "antd";

const { Title } = Typography;

type Props = {
  actions?: React.ReactNode;
  title: string;
};

export function PageHeader({ actions, title }: Props) {
  return (
    <Flex className="page-header section" align="center" justify="space-between" gap={16} wrap>
      <Title level={2} className="page-title">{title}</Title>
      {actions}
    </Flex>
  );
}

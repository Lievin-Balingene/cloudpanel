import { ApiTokensManager } from "@/components/ApiTokensManager";

export function ClientApiPage() {
  return <ApiTokensManager title="Générer une clé API" allowWhm={false} />;
}

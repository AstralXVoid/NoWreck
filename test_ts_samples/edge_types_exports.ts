// Type-level declarations with exports
export interface User {
    id: number;
    name: string;
}

export enum Color {
    Red,
    Green,
}

export type Status = "active" | "inactive";

export default interface Config {
    debug: boolean;
}

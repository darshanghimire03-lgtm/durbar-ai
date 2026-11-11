import { handlers as school } from "./school.js";
import { handlers as notes } from "./notes.js";
import { handlers as mock } from "./mock.js";
import { handlers as people } from "./people.js";
import { handlers as web } from "./web.js";
import { handlers as table } from "./table.js";

export const handlers = { ...school, ...notes, ...mock, ...people, ...web, ...table };
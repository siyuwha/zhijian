export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

export interface DataQuality {
  completeness: number;
  accuracy: number;
  timeliness: number;
}

interface IProps {
  data: {
    name: string;
    url: string;
  };
}

function FileAttach({ data }: IProps) {
  return (
    <div className="file-attach">
      <span className="border border-gray-200 rounded px-1.5 py-1 inline-flex items-center gap-1.5">
        <img
          src="/icons/chat/excel.png"
          alt="excel"
          className="inline-block align-middle w-5 h-5 mr-1"
        />
        <span className="inline-block align-middle whitespace-nowrap">{data.name}</span>
      </span>
    </div>
  );
}

export default FileAttach;

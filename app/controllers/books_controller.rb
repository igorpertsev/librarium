class BooksController < ApplicationController
  def index
    @books = Book.all
  end

  def show
    @book = Book.find(params[:id])
  end

  def new
    @book = Book.new
  end

  def create
    debugger
    @book = Book.new(book_params)
    if @book.save
      params[:book][:genre_ids].each do |genre_id|
        GenresToBook.create(book_id: @book.id, genre_id: genre_id) if genre_id.present?
      end

      respond_to do |format|
        format.html { redirect_to book_path }
        format.turbo_stream
      end
    else
      render :new
    end
  end

  def edit
    @book = Book.find(params[:id])
  end

  def update
    @book = Book.find(params[:id])
    if @book.update(book_params)
      respond_to do |format|
        format.html { redirect_to book_path }
        format.turbo_stream
      end
    else
      render :edit
    end
  end

  def destroy
    @book = Book.find(params[:id])
    @book.destroy
    respond_to do |format|
      format.html { redirect_to books_path }
      format.turbo_stream
    end
  end

  private

  def book_params
    params.require(:book).permit(:title, :author_id, :publisher_id, :published_year, :page_count, :description)
  end
end
